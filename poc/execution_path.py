from __future__ import annotations

from dataclasses import dataclass

from poc.atl_boundary import ATLCommitBoundary, ATLExecutionObject
from poc.commit_gate import CommitGate, SafetyDecision
from poc.gie import CheckResult, Decision, ExecutionEvidence, GIE, make_bytes_execution_evidence
from poc.halos_adapter import HalosAdapter


@dataclass(frozen=True)
class ExecutionPathResult:
    """Result of the complete authority + safety + commit composition."""

    decision: Decision
    reason: str
    packet: bytes | None
    action_digest: str
    execution_epoch: int


class GovernedExecutionPath:
    """Reference composition layer for a governed exact-byte execution path.

    The producer supplies only the concrete execution object and its non-
    authoritative execution epoch. Authority is resolved from GIE-owned state;
    safety is supplied independently and bound to the same execution digest.
    Final authority revalidation happens immediately before the Commit Gate.
    """

    def __init__(self, gie: GIE, env_id: int, gate: CommitGate | None = None) -> None:
        if env_id < 0:
            raise ValueError("env_id must be non-negative")
        self._gie = gie
        self._env_id = env_id
        self._gate = gate or CommitGate()
        self._boundary = ATLCommitBoundary(self._gate)

    @property
    def env_id(self) -> int:
        """Environment whose GIE-owned authority governs this execution path."""
        return self._env_id

    def prepare_authority(
        self,
        execution: ATLExecutionObject,
    ) -> tuple[ExecutionEvidence, CheckResult]:
        """Create non-authoritative evidence and resolve current GIE authority."""
        evidence = make_bytes_execution_evidence(
            env_id=self._env_id,
            payload=execution.packet,
            execution_epoch=execution.governance_epoch,
        )
        authority = self._gie.check_bytes_evidence(evidence, execution.packet)
        return evidence, authority

    def commit(
        self,
        execution: ATLExecutionObject,
        halos_decision: SafetyDecision = SafetyDecision.ALLOW,
        halos_reason: str = "halos_safe",
    ) -> ExecutionPathResult:
        """Run the complete path and return the exact transmit payload on ALLOW."""
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
            execution_digest=execution.packet_digest,
        )

        result = self._boundary.commit(execution, authority, safety)
        payload = self._boundary.transmit_payload(execution, result)
        return ExecutionPathResult(
            decision=result.decision,
            reason=result.reason,
            packet=payload,
            action_digest=result.packet_digest,
            execution_epoch=result.governance_epoch,
        )
