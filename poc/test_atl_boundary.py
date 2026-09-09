import pytest
import torch

from poc.atl_boundary import ATLCommitBoundary, ATLExecutionObject, ATLBoundaryError
from poc.commit_gate import CommitGate, SafetyDecision
from poc.gie import Decision, GIE, make_execution_evidence
from poc.halos_adapter import HalosAdapter


def _inputs():
    gie = GIE()
    epoch = gie.grant(0, epoch=481)
    action = torch.tensor([0.1, 0.2, 0.3])
    evidence = make_execution_evidence(0, action, epoch)
    authority = gie.check_evidence(evidence, action)
    authority = gie.revalidate(0, authority, action)
    packet = bytes(range(64))
    execution = ATLExecutionObject(packet=packet, governance_epoch=epoch)
    safety = HalosAdapter.bind(execution.packet_digest, SafetyDecision.ALLOW, "halos_safe")
    return gie, execution, authority, safety


def test_allow_forwards_exact_original_atl_packet():
    _, execution, authority, safety = _inputs()
    boundary = ATLCommitBoundary(CommitGate())

    # Rebind the authority identity to the exact ATL packet for the transport PoC.
    from dataclasses import replace
    authority = replace(authority, action_digest=execution.packet_digest)

    result = boundary.commit(execution, authority, safety)
    payload = boundary.transmit_payload(execution, result)

    assert result.decision is Decision.ALLOW
    assert payload == execution.packet
    assert payload is execution.packet


def test_block_emits_no_downstream_transmit_payload():
    gie, execution, authority, safety = _inputs()
    boundary = ATLCommitBoundary(CommitGate())
    gie.revoke(0)

    from dataclasses import replace
    authority = replace(authority, decision=Decision.BLOCK, reason="revoked", action_digest=execution.packet_digest)

    result = boundary.commit(execution, authority, safety)
    payload = boundary.transmit_payload(execution, result)

    assert result.decision is Decision.BLOCK
    assert payload is None


def test_same_packet_is_not_authorized_after_governance_epoch_change():
    gie, execution, authority, safety = _inputs()
    boundary = ATLCommitBoundary(CommitGate())
    gie.grant(0, epoch=482)

    from dataclasses import replace
    authority = replace(
        authority,
        decision=Decision.BLOCK,
        reason="epoch_mismatch",
        authority_epoch=482,
        action_digest=execution.packet_digest,
    )

    result = boundary.commit(execution, authority, safety)
    payload = boundary.transmit_payload(execution, result)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_epoch_mismatch"
    assert payload is None
    assert execution.packet == bytes(range(64))


def test_wrong_packet_identity_cannot_cross_boundary():
    _, execution, authority, _ = _inputs()
    boundary = ATLCommitBoundary(CommitGate())
    from dataclasses import replace
    authority = replace(authority, action_digest=execution.packet_digest)
    different = ATLExecutionObject(packet=bytes(reversed(range(64))), governance_epoch=481)
    safety = HalosAdapter.bind(different.packet_digest, SafetyDecision.ALLOW, "halos_safe")

    result = boundary.commit(different, authority, safety)
    payload = boundary.transmit_payload(different, result)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_digest_mismatch"
    assert payload is None


def test_atl_packet_must_be_exactly_64_bytes():
    with pytest.raises(ATLBoundaryError):
        ATLExecutionObject(packet=b"too-short", governance_epoch=481)
