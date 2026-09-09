import torch

from poc.commit_gate import CommitGate, SafetyDecision
from poc.gie import Decision, GIE, make_execution_evidence
from poc.halos_adapter import HalosAdapter


def _inputs():
    gie = GIE()
    epoch = gie.grant(0, epoch=1)
    action = torch.tensor([0.1, 0.2, 0.3])
    evidence = make_execution_evidence(0, action, epoch)
    authority = gie.check_evidence(evidence, action)
    authority = gie.revalidate(0, authority, action)
    return gie, action, evidence, authority


def test_gie_block_and_halos_allow_still_blocks():
    gie, action, evidence, _ = _inputs()
    gie.revoke(0)
    authority = gie.check_evidence(evidence, action)
    safety = HalosAdapter.bind(evidence.action_digest, SafetyDecision.ALLOW, "halos_safe")

    result = CommitGate().commit(evidence.action_digest, authority, safety)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_revoked"


def test_gie_allow_and_halos_block_still_blocks():
    _, _, evidence, authority = _inputs()
    safety = HalosAdapter.bind(evidence.action_digest, SafetyDecision.BLOCK, "unsafe")

    result = CommitGate().commit(evidence.action_digest, authority, safety)

    assert authority.decision is Decision.ALLOW
    assert result.decision is Decision.BLOCK
    assert result.reason == "safety_unsafe"


def test_gie_allow_and_halos_allow_same_action_commits():
    _, _, evidence, authority = _inputs()
    safety = HalosAdapter.bind(evidence.action_digest, SafetyDecision.ALLOW, "halos_safe")

    result = CommitGate().commit(evidence.action_digest, authority, safety)

    assert result.decision is Decision.ALLOW
    assert result.reason == "committable"


def test_halos_result_for_different_action_cannot_commit():
    _, action, evidence, authority = _inputs()
    other_action = action + 1.0
    other_evidence = make_execution_evidence(0, other_action, evidence.action_epoch)
    safety = HalosAdapter.bind(other_evidence.action_digest, SafetyDecision.ALLOW, "halos_safe")

    result = CommitGate().commit(evidence.action_digest, authority, safety)

    assert result.decision is Decision.BLOCK
    assert result.reason == "safety_digest_mismatch"
