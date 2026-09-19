from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from poc.commit_gate import CommitGate, SafetyDecision, SafetyResult
from poc.execution_identity import digest_bytes
from poc.gie import CheckResult, Decision, ExecutionEvidence, GIE, make_bytes_execution_evidence
from poc.halos_adapter import HalosAdapter
from poc.evidence import CommitEvidence, EvidenceRecorder


class ActuatorAdapter(Protocol):
    """Physical I/O adapter used only after a successful Commit Gate decision."""

    def apply(self, payload: bytes) -> None: ...


CommitPayloadFactory = Callable[[bytes, CheckResult], bytes]


@dataclass(frozen=True)
class PhysicalExecutionObject:
    """Hardware-agnostic execution object presented to the Magic Box."""

    env_id: int
    payload: bytes
    execution_epoch: int

    @property
    def action_digest(self) -> str:
        return digest_bytes(self.payload)


@dataclass(frozen=True)
class PhysicalCommitResult:
    decision: Decision
    reason: str
    action_digest: str
    execution_epoch: int
    authority_epoch: int = 0
    applied: bool = False
    command_id: str | None = None


class GovernedPhysicalPath:
    """Generic execution boundary between an autonomous controller and an actuator.

    The governance core is independent of the host CPU, operating system,
    transport, and physical I/O mechanism. The actuator adapter is invoked
    only after authority, safety, identity, environment, and freshness checks
    have all succeeded.
    """

    def __init__(self, gie: GIE, env_id: int, actuator: ActuatorAdapter,
                 gate: CommitGate | None = None,
                 evidence: EvidenceRecorder | None = None) -> None:
        if env_id < 0:
            raise ValueError("env_id must be non-negative")
        self._gie = gie
        self._env_id = env_id
        self._actuator = actuator
        self._gate = gate or CommitGate()
        self._evidence = evidence

    @property
    def env_id(self) -> int:
        return self._env_id

    def prepare_authority(
        self, execution: PhysicalExecutionObject
    ) -> tuple[ExecutionEvidence, CheckResult]:
        """Create non-authoritative evidence and resolve authority in GIE."""
        evidence = make_bytes_execution_evidence(
            env_id=self._env_id,
            payload=execution.payload,
            execution_epoch=execution.execution_epoch,
        )
        authority = self._gie.check_bytes_evidence(evidence, execution.payload)
        return evidence, authority

    def commit(
        self,
        execution: PhysicalExecutionObject,
        halos_decision: SafetyDecision = SafetyDecision.ALLOW,
        halos_reason: str = "halos_safe",
        commit_payload_factory: CommitPayloadFactory | None = None,
        command_id: str | None = None,
    ) -> PhysicalCommitResult:
        """Commit one physical command, or guarantee that no actuator call occurs."""
        if execution.env_id != self._env_id:
            return PhysicalCommitResult(
                Decision.BLOCK,
                "execution_env_mismatch",
                execution.action_digest,
                execution.execution_epoch,
                self._gie.current_epoch(self._env_id),
                False,
                None,
            )

        evidence, authority = self.prepare_authority(execution)
        effective_command_id = command_id or f"pending-{evidence.action_digest[:12]}"
        if self._evidence is not None:
            self._evidence.record(CommitEvidence("PREPARE", effective_command_id, evidence.env_id, evidence.action_digest, execution.execution_epoch, authority.authority_epoch, authority.decision.value, authority.reason, None, None, None, None, None, False, EvidenceRecorder.now()))
        safety = HalosAdapter.bind(
            action_digest=evidence.action_digest,
            decision=halos_decision,
            reason=halos_reason,
        )

        # TOCTOU defense: authority is re-read immediately before the final gate.
        authority = self._gie.revalidate(
            env_id=evidence.env_id,
            authority=authority,
            action=None,
            execution_digest=evidence.action_digest,
        )

        if self._evidence is not None:
            self._evidence.record(CommitEvidence("FINAL_AUTHORITY_CHECK", effective_command_id, evidence.env_id, evidence.action_digest, execution.execution_epoch, authority.authority_epoch, authority.decision.value, authority.reason, safety.decision.value, safety.reason, None, None, None, False, EvidenceRecorder.now()))

        # GIE owns freshness semantics. Do not duplicate or reinterpret the
        # epoch verdict here: STALE_EPOCH must propagate unchanged to the gate.
        decision = self._gate.commit(
            env_id=self._env_id,
            action_digest=execution.action_digest,
            authority=authority,
            safety=safety,
        )
        if decision.decision is Decision.BLOCK:
            if self._evidence is not None:
                self._evidence.record(CommitEvidence("COMMIT", effective_command_id, evidence.env_id, evidence.action_digest, execution.execution_epoch, decision.authority_epoch, authority.decision.value, authority.reason, safety.decision.value, safety.reason, decision.decision.value, decision.reason, "NOT_ATTEMPTED", False, EvidenceRecorder.now()))
            return PhysicalCommitResult(
                Decision.BLOCK,
                decision.reason,
                execution.action_digest,
                execution.execution_epoch,
                decision.authority_epoch,
                False,
                command_id,
            )

        # The commit payload is constructed only after the final gate decision.
        # The actuator API remains deliberately minimal: apply(bytes) only.
        actuator_payload = execution.payload
        if commit_payload_factory is not None:
            actuator_payload = commit_payload_factory(execution.payload, authority)

        try:
            self._actuator.apply(actuator_payload)
        except Exception:
            if self._evidence is not None:
                self._evidence.record(CommitEvidence("EXECUTION", effective_command_id, evidence.env_id, evidence.action_digest, execution.execution_epoch, decision.authority_epoch, authority.decision.value, authority.reason, safety.decision.value, safety.reason, decision.decision.value, decision.reason, "FAILED", False, EvidenceRecorder.now()))
            raise
        if self._evidence is not None:
            self._evidence.record(CommitEvidence("EXECUTION", effective_command_id, evidence.env_id, evidence.action_digest, execution.execution_epoch, decision.authority_epoch, authority.decision.value, authority.reason, safety.decision.value, safety.reason, decision.decision.value, decision.reason, "COMMITTED", True, EvidenceRecorder.now()))
        return PhysicalCommitResult(
            Decision.ALLOW,
            decision.reason,
            execution.action_digest,
            execution.execution_epoch,
            decision.authority_epoch,
            True,
            command_id,
        )


class RecordingRelay:
    """Host-independent relay model for the physical Magic Box PoC."""

    def __init__(self) -> None:
        self.state: bool = False
        self.applied_payloads: list[bytes] = []

    def apply(self, payload: bytes) -> None:
        """Apply an opaque relay command; protocol decoding is outside the core."""
        self.applied_payloads.append(payload)
        self.state = payload == b"RELAY:ON"
