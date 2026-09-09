import torch

from poc.gie import AuthorityContext, Decision, GIE, make_bytes_execution_evidence


def test_h1_generated_does_not_imply_authority():
    gie = GIE()

    result = gie.check(
        env_id=0,
        action=torch.tensor([1.0, 2.0]),
        action_epoch=1,
    )

    assert result.decision is Decision.BLOCK
    assert result.reason == "no_authority_context"


def test_h2_per_action_check_observes_current_authority():
    gie = GIE()
    epoch = gie.grant(0)
    action = torch.tensor([1.0])

    first = gie.check(0, action, epoch)
    assert first.decision is Decision.ALLOW

    gie.revoke(0)
    second = gie.check(0, action, epoch)
    assert second.decision is Decision.BLOCK
    assert second.reason == "revoked"


def test_h3_revocation_invalidates_cached_epoch():
    gie = GIE()
    epoch = gie.grant(0)
    cached_action = torch.tensor([0.5, -0.25])

    gie.revoke(0)
    result = gie.check(0, cached_action, action_epoch=epoch)

    assert result.decision is Decision.BLOCK
    assert result.action_epoch == epoch
    assert result.authority_epoch == epoch


def test_reauthorization_creates_new_epoch():
    gie = GIE()
    epoch_1 = gie.grant(0)
    gie.revoke(0)
    epoch_2 = gie.grant(0)

    assert epoch_2 == epoch_1 + 1

    old_action = torch.tensor([1.0])
    new_action = torch.tensor([2.0])

    old_result = gie.check(0, old_action, action_epoch=epoch_1)
    new_result = gie.check(0, new_action, action_epoch=epoch_2)

    assert old_result.decision is Decision.BLOCK
    assert old_result.reason == "epoch_mismatch"
    assert new_result.decision is Decision.ALLOW


def test_explicit_context_can_be_checked_without_mutating_gie_state():
    gie = GIE()
    action = torch.tensor([0.0])

    result = gie.check(
        env_id=7,
        action=action,
        action_epoch=4,
        authority_context=AuthorityContext(epoch=4, revoked=False),
    )

    assert result.decision is Decision.ALLOW
    assert gie.current_epoch(7) == 0


def test_byte_execution_identity_is_non_authoritative_evidence():
    gie = GIE()
    epoch = gie.grant(0, epoch=481)
    packet = bytes(range(64))
    evidence = make_bytes_execution_evidence(0, packet, epoch)

    result = gie.check_bytes_evidence(evidence, packet)

    assert result.decision is Decision.ALLOW
    assert result.action_epoch == 481
    assert result.authority_epoch == 481
    assert result.action_digest == evidence.action_digest
