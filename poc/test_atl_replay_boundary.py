from __future__ import annotations

from poc.atl_boundary import ATLCommitBoundary, ATLExecutionObject
from poc.commit_gate import CommitGate, SafetyDecision, SafetyResult
from poc.gie import Decision, GIE, make_bytes_execution_evidence


class MockATLReceiver:
    """Minimal downstream receiver that records transmitted ATL packets."""

    def __init__(self) -> None:
        self.received: list[bytes] = []

    def transmit(self, packet: bytes | None) -> None:
        if packet is not None:
            self.received.append(packet)


def commit_atl(
    gie: GIE,
    boundary: ATLCommitBoundary,
    receiver: MockATLReceiver,
    packet: bytes,
    epoch: int,
) -> Decision:
    """Run one exact-packet execution through GIE, safety, and Commit Gate."""
    execution = ATLExecutionObject(packet=packet, governance_epoch=epoch)
    evidence = make_bytes_execution_evidence(0, packet, epoch)
    authority = gie.check_bytes_evidence(evidence, packet)
    safety = SafetyResult(SafetyDecision.ALLOW, "halos_safe", execution.packet_digest)
    result = boundary.commit(execution, authority, safety)
    receiver.transmit(boundary.transmit_payload(execution, result))
    return result.decision


def test_exact_atl_packet_replay_is_blocked_after_authority_epoch_changes():
    gie = GIE()
    epoch_481 = gie.grant(0, epoch=481)
    boundary = ATLCommitBoundary(CommitGate())
    receiver = MockATLReceiver()

    # Representative exact 64-byte ATL command. The boundary treats it as
    # opaque bytes and does not parse, rewrite, or regenerate protocol fields.
    packet = bytes(range(64))

    assert commit_atl(gie, boundary, receiver, packet, epoch_481) is Decision.ALLOW
    assert receiver.received == [packet]

    # Authority changes after the packet was validly observed.
    gie.revoke(0)
    epoch_482 = gie.grant(0, epoch=482)

    # The exact same bytes are replayed with stale execution evidence.
    execution = ATLExecutionObject(packet=packet, governance_epoch=epoch_481)
    evidence = make_bytes_execution_evidence(0, packet, epoch_481)
    authority = gie.check_bytes_evidence(evidence, packet)
    safety = SafetyResult(SafetyDecision.ALLOW, "halos_safe", execution.packet_digest)
    result = boundary.commit(execution, authority, safety)
    receiver.transmit(boundary.transmit_payload(execution, result))

    assert epoch_482 == 482
    assert authority.decision is Decision.BLOCK
    assert authority.reason == "epoch_mismatch"
    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_epoch_mismatch"
    assert receiver.received == [packet]


def test_allowed_atl_transmission_preserves_exact_original_bytes():
    gie = GIE()
    epoch = gie.grant(0, epoch=481)
    boundary = ATLCommitBoundary(CommitGate())
    receiver = MockATLReceiver()
    packet = b"HALOS-ATL" + bytes(range(55))

    assert commit_atl(gie, boundary, receiver, packet, epoch) is Decision.ALLOW
    assert receiver.received[0] == packet
    assert len(receiver.received[0]) == 64
