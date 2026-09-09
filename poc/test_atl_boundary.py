import pytest

from poc.atl_boundary import ATLCommitBoundary, ATLExecutionObject, ATLBoundaryError
from poc.commit_gate import CommitGate, SafetyDecision
from poc.gie import Decision, GIE, make_bytes_execution_evidence
from poc.halos_adapter import HalosAdapter


def _inputs():
    gie = GIE()
    epoch = gie.grant(0, epoch=481)
    packet = bytes(range(64))
    evidence = make_bytes_execution_evidence(0, packet, epoch)
    authority = gie.check_bytes_evidence(evidence, packet)
    authority = gie.revalidate(0, authority, action=None)
    execution = ATLExecutionObject(env_id=0, packet=packet, governance_epoch=epoch)
    safety = HalosAdapter.bind(execution.packet_digest, SafetyDecision.ALLOW, "halos_safe")
    return gie, execution, authority, safety


def test_allow_forwards_exact_original_atl_packet():
    _, execution, authority, safety = _inputs()
    boundary = ATLCommitBoundary(CommitGate())

    result = boundary.commit(execution, authority, safety)
    payload = boundary.transmit_payload(execution, result)

    assert result.decision is Decision.ALLOW
    assert payload == execution.packet
    assert payload is execution.packet


def test_block_emits_no_downstream_transmit_payload():
    gie, execution, authority, safety = _inputs()
    boundary = ATLCommitBoundary(CommitGate())
    gie.revoke(0)
    authority = gie.revalidate(0, authority, action=None)

    result = boundary.commit(execution, authority, safety)
    payload = boundary.transmit_payload(execution, result)

    assert result.decision is Decision.BLOCK
    assert payload is None


def test_same_packet_is_not_authorized_after_governance_epoch_change():
    gie, execution, authority, safety = _inputs()
    boundary = ATLCommitBoundary(CommitGate())
    gie.grant(0, epoch=482)
    authority = gie.revalidate(0, authority, action=None)

    result = boundary.commit(execution, authority, safety)
    payload = boundary.transmit_payload(execution, result)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_epoch_mismatch"
    assert payload is None
    assert execution.packet == bytes(range(64))


def test_wrong_packet_identity_cannot_cross_boundary():
    _, execution, authority, _ = _inputs()
    boundary = ATLCommitBoundary(CommitGate())
    different = ATLExecutionObject(
        env_id=0,
        packet=bytes(reversed(range(64))),
        governance_epoch=481,
    )
    safety = HalosAdapter.bind(different.packet_digest, SafetyDecision.ALLOW, "halos_safe")

    result = boundary.commit(different, authority, safety)
    payload = boundary.transmit_payload(different, result)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_digest_mismatch"
    assert payload is None


def test_cross_environment_authority_cannot_cross_atl_boundary():
    _, execution, authority, _ = _inputs()
    boundary = ATLCommitBoundary(CommitGate())
    other_environment = ATLExecutionObject(
        env_id=1,
        packet=execution.packet,
        governance_epoch=execution.governance_epoch,
    )
    safety = HalosAdapter.bind(other_environment.packet_digest, SafetyDecision.ALLOW, "halos_safe")

    result = boundary.commit(other_environment, authority, safety)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_env_mismatch"


def test_atl_packet_must_be_exactly_64_bytes():
    with pytest.raises(ATLBoundaryError):
        ATLExecutionObject(env_id=0, packet=b"too-short", governance_epoch=481)
