from poc.atl_boundary import ATLCommitBoundary, ATLExecutionObject
from poc.commit_gate import CommitGate, SafetyDecision, SafetyResult
from poc.gie import Decision, GIE, make_bytes_execution_evidence


class MockATLReceiver:
    """Minimal downstream sink; it must never see a blocked packet."""

    def __init__(self) -> None:
        self.received: list[bytes] = []

    def transmit(self, payload: bytes | None) -> None:
        if payload is not None:
            self.received.append(payload)


def _commit_packet(gie: GIE, boundary: ATLCommitBoundary, receiver: MockATLReceiver, packet: bytes, epoch: int):
    execution = ATLExecutionObject(env_id=0, packet=packet, governance_epoch=epoch)
    evidence = make_bytes_execution_evidence(0, packet, epoch)

    authority = gie.check_bytes_evidence(evidence, packet)
    safety = SafetyResult(
        SafetyDecision.ALLOW,
        "halos_safe",
        evidence.action_digest,
    )
    result = boundary.commit(execution, authority, safety)
    receiver.transmit(boundary.transmit_payload(execution, result))
    return result


def test_end_to_end_atl_replay_is_blocked_after_authority_epoch_change():
    """Prove the complete execution-boundary invariant with an exact ATL replay."""
    gie = GIE()
    gate = CommitGate()
    boundary = ATLCommitBoundary(gate)
    receiver = MockATLReceiver()

    epoch_481 = gie.grant(0, epoch=481)
    packet = bytes(range(64))

    first = _commit_packet(gie, boundary, receiver, packet, epoch_481)

    assert first.decision is Decision.ALLOW
    assert first.reason == "committable"
    assert receiver.received == [packet]

    # Authority changes after the first valid execution.
    gie.revoke(0)
    epoch_482 = gie.grant(0, epoch=482)
    assert epoch_482 == 482

    # Replay the exact same 64-byte packet with stale epoch-481 evidence.
    stale = _commit_packet(gie, boundary, receiver, packet, epoch_481)

    assert stale.decision is Decision.BLOCK
    assert stale.reason == "authority_epoch_mismatch"
    assert receiver.received == [packet]


def test_end_to_end_block_produces_zero_transmit_payload():
    gie = GIE()
    boundary = ATLCommitBoundary(CommitGate())
    receiver = MockATLReceiver()

    epoch = gie.grant(0, epoch=481)
    packet = b"H" * 64
    execution = ATLExecutionObject(env_id=0, packet=packet, governance_epoch=epoch)
    evidence = make_bytes_execution_evidence(0, packet, epoch)

    gie.revoke(0)
    authority = gie.check_bytes_evidence(evidence, packet)
    safety = SafetyResult(SafetyDecision.ALLOW, "halos_safe", evidence.action_digest)
    result = boundary.commit(execution, authority, safety)

    assert result.decision is Decision.BLOCK
    assert boundary.transmit_payload(execution, result) is None
    receiver.transmit(boundary.transmit_payload(execution, result))
    assert receiver.received == []


def test_end_to_end_allow_forwards_exact_original_packet_bytes():
    gie = GIE()
    boundary = ATLCommitBoundary(CommitGate())
    receiver = MockATLReceiver()

    epoch = gie.grant(0, epoch=481)
    packet = bytes(reversed(range(64)))
    result = _commit_packet(gie, boundary, receiver, packet, epoch)

    assert result.decision is Decision.ALLOW
    assert receiver.received[0] is packet
    assert receiver.received[0] == packet
