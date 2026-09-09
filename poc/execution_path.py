from __future__ import annotations

from dataclasses import dataclass

from poc.atl_boundary import ATLCommitBoundary
from poc.commit_gate import CommitGate, SafetyDecision
from poc.execution_identity import digest_bytes
from poc.gie import CheckResult, Decision, ExecutionEvidence, GIE, make_bytes_execution_evidence
from poc.halos_adapter import HalosAdapter
from poc.sdm_boundary import SDMCommand, SDMCommitAdapter


@dataclass(frozen=True)
class ExecutionPathResult:
    """Result of the complete authority + safety + commit composition."""

    decision: Decision
    reason: str
    packet: bytes | None
    action_digest: str
    execution_epoch: int


class GovernedExecutionPath:
    """Canonical SDM → GIE → Halos → Commit Gate execution composition.

    The SDM command is treated as the exact execution object. Authority is
    resolved from GIE-owned state, safety is supplied independently, and final
    authority revalidation occurs immediately before the Commit Gate.
    """

    def __init__(self, gie: GIE, env_id: int, gate: CommitGate | None = None) -> None:
        if env_id < 0:
            raise ValueError("env_id must be non-negative")
        self._gie = gie
        self._env_id = env_id
        self._gate = gate or CommitGate()
        self._adapter = SDMCommitAdapter(ATLCommitBoundary(self._gate))

    @property
    def env_id(self) -> int:
        return self._env_id

    def prepare_authority(
        self,
        command: SDMCommand,
    ) -> tuple[ExecutionEvidence, CheckResult]:
        """Bind non-authoritative execution evidence and resolve GIE authority."""
        evidence = make_bytes_execution_evidence(
            env_id=self._env_id,
            payload=command.packet,
            execution_epoch=command.governance_epoch,
        )
        authority = self._gie.check_bytes_evidence(evidence, command.packet)
        return evidence, authority

    def commit(
        self,
        command: SDMCommand,
        halos_decision: SafetyDecision = SafetyDecision.ALLOW,
        halos_reason: str = "halos_safe",
    ) -> ExecutionPathResult:
        """Run the canonical path and return the exact SDM packet on ALLOW."""
        # The command must belong to the execution environment represented by
        # this path. Do not let a lower boundary discover this mismatch after
        # authority has already been resolved for a different environment.
        if command.env_id != self._env_id:
            return ExecutionPathResult(
                decision=Decision.BLOCK,
                reason="execution_env_mismatch",
                packet=None,
                action_digest=digest_bytes(command.packet),
                execution_epoch=command.governance_epoch,
            )

        evidence, authority = self.prepare_authority(command)
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

        result = self._adapter.commit(command, authority, safety)
        payload = self._adapter.transmit_payload(command, result)
        return ExecutionPathResult(
            decision=result.decision,
            reason=result.reason,
            packet=payload,
            action_digest=result.packet_digest,
            execution_epoch=result.governance_epoch,
        )
