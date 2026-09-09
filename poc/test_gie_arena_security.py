from __future__ import annotations

import torch

from poc.gie import AuthorityContext, Decision, GIE



def test_check_uses_internal_gie_state_not_caller_context_when_bound_for_arena():
    """Arena-facing contract: authority cannot be supplied by policy/scheduler code."""
    gie = GIE()
    gie.grant(0, epoch=7)

    forged_context = AuthorityContext(epoch=999, revoked=False)

    # The public GIE primitive still supports explicit contexts for isolated tests.
    # Arena integration MUST NOT expose that argument. This test defines the
    # security property the adapter must preserve: caller-supplied authority
    # cannot become the source of truth for the Arena execution path.
    result = gie.check(
        env_id=0,
        action=torch.ones(4),
        action_epoch=7,
    )
    assert result.decision is Decision.ALLOW
    assert result.authority_epoch == 7

    gie.revoke(0)
    result = gie.check(
        env_id=0,
        action=torch.ones(4),
        action_epoch=7,
    )
    assert result.decision is Decision.BLOCK
    assert result.reason == "revoked"

    # A forged context would otherwise turn the same revoked action into ALLOW.
    forged_result = gie.check(
        env_id=0,
        action=torch.ones(4),
        action_epoch=999,
        authority_context=forged_context,
    )
    assert forged_result.decision is Decision.ALLOW



def test_arena_boundary_has_no_authority_context_parameter():
    """The scheduler-facing adapter API must not accept AuthorityContext."""
    from inspect import signature
    from poc.gie_action_chunk_scheduler import GIEActionChunkScheduler

    params = signature(GIEActionChunkScheduler.get_action).parameters
    assert "authority_context" not in params



def test_reset_does_not_grant_authority():
    """Reset is lifecycle invalidation, never an implicit authority grant."""
    gie = GIE()
    gie.grant(0, epoch=3)
    gie.revoke(0)

    # Model the state observed by an Arena adapter after reset: no authority
    # transition is performed by reset itself.
    assert gie.current_epoch(0) == 3
    result = gie.check(
        env_id=0,
        action=torch.zeros(4),
        action_epoch=3,
    )
    assert result.decision is Decision.BLOCK
    assert result.reason == "revoked"
