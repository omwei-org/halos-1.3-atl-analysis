from __future__ import annotations

from poc.commit_gate import SafetyDecision, SafetyResult


class HalosAdapter:
    """Boundary adapter for a Halos-derived safety decision.

    The adapter deliberately does not implement or emulate Halos safety logic.
    It binds an externally produced Halos decision to the exact execution
    object's digest so the Commit Gate can enforce conjunction without making
    the safety subsystem an authority issuer.
    """

    @staticmethod
    def bind(
        action_digest: str,
        decision: SafetyDecision,
        reason: str,
    ) -> SafetyResult:
        """Convert a Halos decision into the neutral Commit Gate contract."""
        return SafetyResult(decision=decision, reason=reason, action_digest=action_digest)
