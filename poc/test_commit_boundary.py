import torch

from poc.commit_gate import CommitGate, SafetyDecision, SafetyResult
from poc.gie import Decision, GIE, make_execution_evidence


def test_stale_allow_cannot_cross_commit_after_revocation():
    gie = GIE()
    epoch = gie.grant(0, epoch=1)
    gate = CommitGate()
    action = torch.tensor([0.1, 0.2, 0.3])

    evidence = make_execution_evidence(0, action, epoch)
    checked = gie.check_evidence(evidence, action)
    assert checked.decision is Decision.ALLOW

    # TOCTOU window: authority changes after the first check.
    gie.revoke(0)

    final_authority = gie.revalidate(0, checked, action)
    safety = SafetyResult(SafetyDecision.ALLOW, "safe", evidence.action_digest)
    result = gate.commit(evidence.action_digest, final_authority, safety)

    assert final_authority.decision is Decision.BLOCK
    assert final_authority.reason == "revoked"
    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_revoked"


def test_stale_allow_cannot_cross_commit_after_epoch_change():
    gie = GIE()
    epoch_1 = gie.grant(0, epoch=1)
    gate = CommitGate()
    action = torch.tensor([0.4, 0.5, 0.6])

    evidence = make_execution_evidence(0, action, epoch_1)
    checked = gie.check_evidence(evidence, action)
    assert checked.decision is Decision.ALLOW

    gie.revoke(0)
    gie.grant(0, epoch=2)

    final_authority = gie.revalidate(0, checked, action)
    safety = SafetyResult(SafetyDecision.ALLOW, "safe", evidence.action_digest)
    result = gate.commit(evidence.action_digest, final_authority, safety)

    assert final_authority.decision is Decision.BLOCK
    assert final_authority.reason == "epoch_mismatch"
    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_epoch_mismatch"


def test_final_revalidation_preserves_allow_for_current_authority():
    gie = GIE()
    epoch = gie.grant(0, epoch=7)
    gate = CommitGate()
    action = torch.tensor([0.7, 0.8, 0.9])

    evidence = make_execution_evidence(0, action, epoch)
    checked = gie.check_evidence(evidence, action)
    final_authority = gie.revalidate(0, checked, action)
    safety = SafetyResult(SafetyDecision.ALLOW, "safe", evidence.action_digest)
    result = gate.commit(evidence.action_digest, final_authority, safety)

    assert final_authority.decision is Decision.ALLOW
    assert final_authority.authority_epoch == epoch
    assert result.decision is Decision.ALLOW
    assert result.reason == "committable"
