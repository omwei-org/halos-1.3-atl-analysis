from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from poc.commit_gate import CommitGate, SafetyDecision, SafetyResult
from poc.execution_identity import digest_bytes
from poc.gie import CheckResult, Decision, ExecutionEvidence, GIE, make_bytes_execution_evidence
from poc.halos_adapter import HalosAdapter


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
    applied: bool


class GovernedPhysicalPath:
    """Generic execution boundary between an autonomous controller and an actuator.

    The governance core is independent of the host CPU, operating system,
    transport, and physical I/O mechanism. The actuator adapter is invoked
    only after authority, safety, identity, environment, and freshness checks
    have all succeeded.
    """

    def __init__(self, gie: GIE, env_id: int, actuator: ActuatorAdapter,
                 gate: CommitGate | None = None) -> None:
        if env_id < 0:
            raise ValueError("env_id must be non-negative")
        self._gie = gie
        self._env_id = env_id
        self._actuator = actuator
        self._gate = gate or CommitGate()

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
    ) -> PhysicalCommitResult:
        """Commit one physical command, or guarantee that no actuator call occurs."""
        if execution.env_id != self._env_id:
            return PhysicalCommitResult(
                Decision.BLOCK,
                "execution_env_mismatch",
                execution.action_digest,
                execution.execution_epoch,
                False,
            )

        evidence, authority = self.prepare_authority(execution)
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

        if authority.action_epoch != execution.execution_epoch:
            return PhysicalCommitResult(
                Decision.BLOCK,
                "execution_epoch_mismatch",
                execution.action_digest,
                execution.execution_epoch,
                False,
            )

        decision = self._gate.commit(
            env_id=self._env_id,
            action_digest=execution.action_digest,
            authority=authority,
            safety=safety,
        )
        if decision.decision is Decision.BLOCK:
            return PhysicalCommitResult(
                Decision.BLOCK,
                decision.reason,
                execution.action_digest,
                execution.execution_epoch,
                False,
            )

        # The commit payload is constructed only after the final gate decision.
        # The actuator API remains deliberately minimal: apply(bytes) only.
        actuator_payload = execution.payload
        if commit_payload_factory is not None:
            actuator_payload = commit_payload_factory(execution.payload, authority)

        self._actuator.apply(actuator_payload)
        return PhysicalCommitResult(
            Decision.ALLOW,
            decision.reason,
            execution.action_digest,
            execution.execution_epoch,
            True,
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
