from __future__ import annotations

import torch

from poc.commit_gate import CommitGate, SafetyDecision, SafetyResult
from poc.gie import Decision, GIE, make_execution_evidence


class MockActuator:
    """Minimal execution sink used to prove the commit boundary."""

    def __init__(self) -> None:
        self.executed: list[torch.Tensor] = []

    def execute(self, action: torch.Tensor) -> None:
        self.executed.append(action.detach().clone())


def run_commit(gie: GIE, gate: CommitGate, actuator: MockActuator, action: torch.Tensor) -> Decision:
    """Model the execution path after policy inference, without modifying the policy."""
    epoch = gie.current_epoch(0)
    evidence = make_execution_evidence(0, action, epoch)
    authority = gie.check_evidence(evidence, action)
    safety = SafetyResult(SafetyDecision.ALLOW, "safe", evidence.action_digest)

    # TOCTOU defense: authority is re-read immediately before the execution gate.
    authority = gie.revalidate(
        env_id=evidence.env_id,
        authority=authority,
        action=action,
        execution_digest=evidence.action_digest,
    )
    result = gate.commit(evidence.action_digest, authority, safety)

    if result.decision is Decision.ALLOW:
        actuator.execute(action)

    return result.decision


def test_authorized_action_reaches_actuator():
    gie = GIE()
    gie.grant(0, epoch=1)
    gate = CommitGate()
    actuator = MockActuator()
    action = torch.tensor([0.1, 0.2, 0.3, 0.4])

    assert run_commit(gie, gate, actuator, action) is Decision.ALLOW
    assert len(actuator.executed) == 1
    assert torch.equal(actuator.executed[0], action)


def test_revocation_blocks_execution_but_policy_can_continue_inference():
    gie = GIE()
    gie.grant(0, epoch=1)
    gate = CommitGate()
    actuator = MockActuator()

    policy_inference_count = 0
    action_1 = torch.tensor([1.0, 2.0, 3.0, 4.0])
    action_2 = torch.tensor([5.0, 6.0, 7.0, 8.0])

    # First policy output is authorized and commits.
    policy_inference_count += 1
    assert run_commit(gie, gate, actuator, action_1) is Decision.ALLOW

    # Authority is revoked after inference, before the next execution decision.
    gie.revoke(0)

    policy_inference_count += 1
    assert run_commit(gie, gate, actuator, action_2) is Decision.BLOCK

    assert policy_inference_count == 2
    assert len(actuator.executed) == 1
    assert torch.equal(actuator.executed[0], action_1)


def test_cached_action_from_old_epoch_cannot_cross_commit_boundary_after_reauthorization():
    gie = GIE()
    epoch_1 = gie.grant(0, epoch=1)
    gate = CommitGate()
    actuator = MockActuator()
    cached_action = torch.tensor([9.0, 8.0, 7.0, 6.0])

    # Evidence represents an action generated under epoch 1.
    stale_evidence = make_execution_evidence(0, cached_action, epoch_1)

    gie.revoke(0)
    epoch_2 = gie.grant(0, epoch=2)
    assert epoch_2 == 2

    authority = gie.check_evidence(stale_evidence, cached_action)
    safety = SafetyResult(SafetyDecision.ALLOW, "safe", stale_evidence.action_digest)
    authority = gie.revalidate(
        env_id=0,
        authority=authority,
        action=cached_action,
        execution_digest=stale_evidence.action_digest,
    )
    result = gate.commit(stale_evidence.action_digest, authority, safety)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_epoch_mismatch"
    assert actuator.executed == []


def test_new_epoch_action_can_commit_without_restarting_policy():
    gie = GIE()
    gie.grant(0, epoch=1)
    gate = CommitGate()
    actuator = MockActuator()

    # Policy remains a stateless producer in this PoC; authority is renewed externally.
    old_action = torch.tensor([1.0, 1.0, 1.0, 1.0])
    assert run_commit(gie, gate, actuator, old_action) is Decision.ALLOW

    gie.revoke(0)
    gie.grant(0, epoch=2)

    new_action = torch.tensor([2.0, 2.0, 2.0, 2.0])
    assert run_commit(gie, gate, actuator, new_action) is Decision.ALLOW

    assert len(actuator.executed) == 2
    assert torch.equal(actuator.executed[-1], new_action)
