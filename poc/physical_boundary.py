from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol
import hashlib
import json

from poc.commit_gate import CommitGate, SafetyDecision, SafetyResult
from poc.execution_identity import digest_bytes
from poc.gie import CheckResult, Decision, ExecutionEvidence, GIE, make_bytes_execution_evidence
from poc.halos_adapter import HalosAdapter
from poc.evidence import CommitEvidence, EffectCorrelationEvidence, EvidenceRecorder


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


@dataclass(frozen=True)
class PreparedPhysicalExecution:
    """Prepared execution state held between authority evaluation and commit."""

    execution: PhysicalExecutionObject
    evidence: ExecutionEvidence
    authority: CheckResult
    safety: SafetyResult
    command_id: str
    commit_payload_factory: CommitPayloadFactory | None = None


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
        """Create execution evidence and resolve the current authority."""
        evidence = make_bytes_execution_evidence(
            env_id=self._env_id,
            payload=execution.payload,
            execution_epoch=execution.execution_epoch,
        )
        authority = self._gie.check_bytes_evidence(evidence, execution.payload)
        return evidence, authority

    def prepare(
        self,
        execution: PhysicalExecutionObject,
        halos_decision: SafetyDecision = SafetyDecision.ALLOW,
        halos_reason: str = "halos_safe",
        commit_payload_factory: CommitPayloadFactory | None = None,
        command_id: str | None = None,
    ) -> PreparedPhysicalExecution:
        """Prepare an execution without crossing the physical-effect boundary."""
        if execution.env_id != self._env_id:
            raise ValueError("execution_env_mismatch")

        evidence, authority = self.prepare_authority(execution)
        effective_command_id = command_id or f"pending-{evidence.action_digest[:12]}"
        safety = HalosAdapter.bind(
            action_digest=evidence.action_digest,
            decision=halos_decision,
            reason=halos_reason,
        )

        if self._evidence is not None:
            self._evidence.record(CommitEvidence(
                "PREPARE", effective_command_id, evidence.env_id,
                evidence.action_digest, execution.execution_epoch,
                authority.authority_epoch, authority.decision.value,
                authority.reason, None, None, None, None, None, False,
                EvidenceRecorder.now(), "", "",
            ))

        return PreparedPhysicalExecution(
            execution=execution,
            evidence=evidence,
            authority=authority,
            safety=safety,
            command_id=effective_command_id,
            commit_payload_factory=commit_payload_factory,
        )

    def commit_prepared(
        self, prepared: PreparedPhysicalExecution
    ) -> PhysicalCommitResult:
        """Revalidate authority and cross the physical-effect boundary if allowed."""
        execution = prepared.execution
        evidence = prepared.evidence
        safety = prepared.safety
        command_id = prepared.command_id

        # TOCTOU defense: authority is re-read immediately before the final gate.
        authority = self._gie.revalidate(
            env_id=evidence.env_id,
            authority=prepared.authority,
            action=None,
            execution_digest=evidence.action_digest,
        )

        if self._evidence is not None:
            self._evidence.record(CommitEvidence(
                "FINAL_AUTHORITY_CHECK", command_id, evidence.env_id,
                evidence.action_digest, execution.execution_epoch,
                authority.authority_epoch, authority.decision.value,
                authority.reason, safety.decision.value, safety.reason,
                None, None, None, False, EvidenceRecorder.now(), "", "",
            ))

        decision = self._gate.commit(
            env_id=self._env_id,
            action_digest=execution.action_digest,
            authority=authority,
            safety=safety,
        )

        if decision.decision is Decision.BLOCK:
            if self._evidence is not None:
                self._evidence.record(CommitEvidence(
                    "COMMIT", command_id, evidence.env_id,
                    evidence.action_digest, execution.execution_epoch,
                    decision.authority_epoch, authority.decision.value,
                    authority.reason, safety.decision.value, safety.reason,
                    decision.decision.value, decision.reason,
                    "NOT_ATTEMPTED", False, EvidenceRecorder.now(), "", "",
                ))
            return PhysicalCommitResult(
                Decision.BLOCK, decision.reason, execution.action_digest,
                execution.execution_epoch, decision.authority_epoch,
                False, command_id,
            )

        # The commit payload is constructed only after the final gate decision.
        actuator_payload = execution.payload
        if prepared.commit_payload_factory is not None:
            actuator_payload = prepared.commit_payload_factory(
                execution.payload, authority
            )

        try:
            self._actuator.apply(actuator_payload)
        except Exception:
            if self._evidence is not None:
                self._evidence.record(CommitEvidence(
                    "EXECUTION", command_id, evidence.env_id,
                    evidence.action_digest, execution.execution_epoch,
                    decision.authority_epoch, authority.decision.value,
                    authority.reason, safety.decision.value, safety.reason,
                    decision.decision.value, decision.reason,
                    "FAILED", False, EvidenceRecorder.now(), "", "",
                ))
            raise

        if self._evidence is not None:
            execution_timestamp = EvidenceRecorder.now()
            self._evidence.record(CommitEvidence(
                "EXECUTION", command_id, evidence.env_id,
                evidence.action_digest, execution.execution_epoch,
                decision.authority_epoch, authority.decision.value,
                authority.reason, safety.decision.value, safety.reason,
                decision.decision.value, decision.reason,
                "COMMITTED", True, execution_timestamp, "", "",
            ))

            # The PoC relay exposes a deterministic observation. This record is
            # deliberately separate from CommitEvidence: it binds the exact
            # actuator bytes and observed state without claiming physical-world
            # attestation beyond the adapter's observation boundary.
            if hasattr(self._actuator, "observe"):
                observation = self._actuator.observe()
                observed_at = EvidenceRecorder.now()
                actuator_payload_digest = digest_bytes(actuator_payload)
                effect_material = json.dumps(
                    {
                        "command_id": command_id,
                        "env_id": evidence.env_id,
                        "actuator_payload_digest": actuator_payload_digest,
                        "observation": observation,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                effect_digest = hashlib.sha256(effect_material).hexdigest()
                self._evidence.record_effect_correlation(EffectCorrelationEvidence(
                    "EFFECT_CORRELATION", command_id, evidence.env_id,
                    evidence.action_digest, actuator_payload_digest,
                    effect_digest, "OBSERVED", observed_at,
                    type(self._actuator).__name__, "", "",
                ))

        return PhysicalCommitResult(
            Decision.ALLOW, decision.reason, execution.action_digest,
            execution.execution_epoch, decision.authority_epoch,
            True, command_id,
        )

    def commit(
        self,
        execution: PhysicalExecutionObject,
        halos_decision: SafetyDecision = SafetyDecision.ALLOW,
        halos_reason: str = "halos_safe",
        commit_payload_factory: CommitPayloadFactory | None = None,
        command_id: str | None = None,
    ) -> PhysicalCommitResult:
        """Backward-compatible prepare-then-commit convenience operation."""
        if execution.env_id != self._env_id:
            return PhysicalCommitResult(
                Decision.BLOCK,
                "execution_env_mismatch",
                execution.action_digest,
                execution.execution_epoch,
                self._gie.current_epoch(self._env_id),
                False,
                command_id,
            )

        prepared = self.prepare(
            execution,
            halos_decision=halos_decision,
            halos_reason=halos_reason,
            commit_payload_factory=commit_payload_factory,
            command_id=command_id,
        )
        return self.commit_prepared(prepared)


class RecordingRelay:
    """Host-independent relay model for the physical Magic Box PoC."""

    def __init__(self) -> None:
        self.state: bool = False
        self.applied_payloads: list[bytes] = []

    def apply(self, payload: bytes) -> None:
        """Apply an opaque relay command; protocol decoding is outside the core."""
        self.applied_payloads.append(payload)
        self.state = payload == b"RELAY:ON"

    def observe(self) -> dict[str, object]:
        """Return the relay's deterministic PoC observation state."""
        return {
            "applied_payload_digest": digest_bytes(self.applied_payloads[-1]) if self.applied_payloads else None,
            "state": self.state,
        }
