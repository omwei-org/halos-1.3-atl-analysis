from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from poc.gie import CheckResult, Decision


class SafetyDecision(Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class SafetyResult:
    """Safety result bound to the concrete execution object."""

    decision: SafetyDecision
    reason: str
    action_digest: str


@dataclass(frozen=True)
class CommitDecision:
    """Final execution-boundary decision.

    The commit gate does not establish authority or safety. It only enforces that
    both independent decisions allow the exact same execution object.
    """

    decision: Decision
    reason: str
    action_digest: str
    authority_epoch: int


class CommitGate:
    """Minimal conjunction gate for authority, safety, and execution identity."""

    def commit(
        self,
        action_digest: str,
        authority: CheckResult,
        safety: SafetyResult,
    ) -> CommitDecision:
        """Allow execution only when authority and safety bind to this action."""
        if authority.decision is not Decision.ALLOW:
            return CommitDecision(
                Decision.BLOCK,
                f"authority_{authority.reason}",
                action_digest,
                authority.authority_epoch,
            )

        if safety.decision is not SafetyDecision.ALLOW:
            return CommitDecision(
                Decision.BLOCK,
                f"safety_{safety.reason}",
                action_digest,
                authority.authority_epoch,
            )

        if safety.action_digest != action_digest:
            return CommitDecision(
                Decision.BLOCK,
                "safety_digest_mismatch",
                action_digest,
                authority.authority_epoch,
            )

        return CommitDecision(
            Decision.ALLOW,
            "committable",
            action_digest,
            authority.authority_epoch,
        )
