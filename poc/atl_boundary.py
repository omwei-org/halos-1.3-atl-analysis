from __future__ import annotations

from dataclasses import dataclass

from poc.commit_gate import CommitGate, SafetyResult
from poc.execution_identity import ExecutionIdentity, digest_bytes
from poc.gie import CheckResult, Decision


ATL_PACKET_SIZE = 64


class ATLBoundaryError(ValueError):
    """Raised when an ATL execution object violates the boundary contract."""


@dataclass(frozen=True)
class ATLExecutionObject:
    """Exact ATL bytes plus non-authoritative execution identity."""

    packet: bytes
    governance_epoch: int

    def __post_init__(self) -> None:
        if len(self.packet) != ATL_PACKET_SIZE:
            raise ATLBoundaryError(
                f"ATL packet must be exactly {ATL_PACKET_SIZE} bytes, got {len(self.packet)}"
            )

    @property
    def identity(self) -> ExecutionIdentity:
        return ExecutionIdentity(
            digest=digest_bytes(self.packet),
            execution_epoch=self.governance_epoch,
        )

    @property
    def packet_digest(self) -> str:
        return self.identity.digest


@dataclass(frozen=True)
class ATLCommitResult:
    decision: Decision
    reason: str
    packet_digest: str
    governance_epoch: int


class ATLCommitBoundary:
    """Final pre-transmission boundary for an exact Halos ATL packet.

    The boundary never rewrites an ATL packet. ALLOW returns the original
    packet bytes; BLOCK returns no transmit payload. Authority and safety
    remain external inputs and are combined by CommitGate.
    """

    def __init__(self, commit_gate: CommitGate) -> None:
        self._commit_gate = commit_gate

    def commit(
        self,
        execution: ATLExecutionObject,
        authority: CheckResult,
        safety: SafetyResult,
    ) -> ATLCommitResult:
        if authority.action_epoch != execution.governance_epoch:
            return ATLCommitResult(
                Decision.BLOCK,
                "execution_epoch_mismatch",
                execution.packet_digest,
                execution.governance_epoch,
            )

        decision = self._commit_gate.commit(
            env_id=authority.env_id,
            action_digest=execution.packet_digest,
            authority=authority,
            safety=safety,
        )
        if decision.decision is Decision.BLOCK:
            return ATLCommitResult(
                Decision.BLOCK,
                decision.reason,
                execution.packet_digest,
                execution.governance_epoch,
            )
        return ATLCommitResult(
            Decision.ALLOW,
            decision.reason,
            execution.packet_digest,
            execution.governance_epoch,
        )

    @staticmethod
    def transmit_payload(
        execution: ATLExecutionObject,
        result: ATLCommitResult,
    ) -> bytes | None:
        """Return the exact original packet only after an ALLOW decision."""
        if result.decision is Decision.BLOCK:
            return None
        if result.packet_digest != execution.packet_digest:
            raise ATLBoundaryError("commit result is not bound to this packet")
        if result.governance_epoch != execution.governance_epoch:
            raise ATLBoundaryError("commit result is not bound to this execution epoch")
        return execution.packet
