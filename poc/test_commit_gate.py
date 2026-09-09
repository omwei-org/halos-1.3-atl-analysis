from __future__ import annotations

import torch

from poc.commit_gate import CommitGate, SafetyDecision, SafetyResult
from poc.gie import CheckResult, Decision, GIE, make_execution_evidence


def authorized_result():
    gie = GIE()
    epoch = gie.grant(0, epoch=7)
    action = torch.tensor([1.0, 2.0])
    evidence = make_execution_evidence(0, action, epoch)
    authority = gie.check_evidence(evidence, action)
    return action, evidence, authority


def test_authority_and_safety_allow_commits_same_action():
    _, evidence, authority = authorized_result()
    safety = SafetyResult(SafetyDecision.ALLOW, "safe", evidence.action_digest)

    result = CommitGate().commit(0, evidence.action_digest, authority, safety)

    assert result.decision is Decision.ALLOW
    assert result.reason == "committable"
    assert result.action_digest == evidence.action_digest


def test_authority_block_prevents_commit_even_when_safe():
    action, evidence, _ = authorized_result()
    gie = GIE()
    gie.grant(0, epoch=7)
    gie.revoke(0)
    blocked_authority = gie.check_evidence(evidence, action)
    safety = SafetyResult(SafetyDecision.ALLOW, "safe", evidence.action_digest)

    result = CommitGate().commit(0, evidence.action_digest, blocked_authority, safety)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_revoked"


def test_safety_block_prevents_commit_even_when_authorized():
    _, evidence, authority = authorized_result()
    safety = SafetyResult(SafetyDecision.BLOCK, "unsafe", evidence.action_digest)

    result = CommitGate().commit(0, evidence.action_digest, authority, safety)

    assert result.decision is Decision.BLOCK
    assert result.reason == "safety_unsafe"


def test_safety_for_different_action_cannot_commit():
    _, evidence, authority = authorized_result()
    safety = SafetyResult(SafetyDecision.ALLOW, "safe", "different-digest")

    result = CommitGate().commit(0, evidence.action_digest, authority, safety)

    assert result.decision is Decision.BLOCK
    assert result.reason == "safety_digest_mismatch"


def test_authority_for_different_action_cannot_commit():
    """I-08: authority for one execution object cannot authorize another."""
    _, evidence, authority = authorized_result()
    different_digest = "different-authorized-digest"
    mismatched_authority = CheckResult(
        decision=Decision.ALLOW,
        reason="authorized",
        env_id=authority.env_id,
        action_epoch=authority.action_epoch,
        authority_epoch=authority.authority_epoch,
        action_digest=different_digest,
    )
    safety = SafetyResult(SafetyDecision.ALLOW, "safe", different_digest)

    result = CommitGate().commit(0, evidence.action_digest, mismatched_authority, safety)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_digest_mismatch"


def test_commit_gate_requires_both_authority_and_safety_for_same_digest():
    """I-09/I-10: safety is independently bound to the exact execution identity."""
    _, evidence, authority = authorized_result()
    safety = SafetyResult(SafetyDecision.ALLOW, "safe", "different-safety-digest")

    result = CommitGate().commit(0, evidence.action_digest, authority, safety)

    assert result.decision is Decision.BLOCK
    assert result.reason == "safety_digest_mismatch"


def test_commit_gate_does_not_convert_safety_into_authority():
    _, evidence, authority = authorized_result()
    blocked_authority = type(authority)(
        decision=Decision.BLOCK,
        reason="epoch_mismatch",
        env_id=authority.env_id,
        action_epoch=authority.action_epoch,
        authority_epoch=authority.authority_epoch + 1,
        action_digest=evidence.action_digest,
    )
    safety = SafetyResult(SafetyDecision.ALLOW, "safe", evidence.action_digest)

    result = CommitGate().commit(0, evidence.action_digest, blocked_authority, safety)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_epoch_mismatch"


def test_authority_from_different_environment_cannot_commit():
    _, evidence, authority = authorized_result()
    safety = SafetyResult(SafetyDecision.ALLOW, "safe", evidence.action_digest)

    result = CommitGate().commit(1, evidence.action_digest, authority, safety)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_env_mismatch"
