from __future__ import annotations

from poc.commit_gate import Decision, SafetyDecision
from poc.atl_boundary import ATLExecutionObject
from poc.execution_path import GovernedExecutionPath
from poc.gie import GIE


class MockATLReceiver:
    def __init__(self) -> None:
        self.received: list[bytes] = []

    def transmit(self, payload: bytes | None) -> None:
        if payload is not None:
            self.received.append(payload)


def test_reference_path_blocks_stale_execution_after_authority_change():
    gie = GIE()
    epoch_1 = gie.grant(0, epoch=481)
    path = GovernedExecutionPath(gie)
    receiver = MockATLReceiver()
    packet = bytes(range(64))

    first = path.commit(ATLExecutionObject(packet, epoch_1))
    receiver.transmit(first.packet)

    assert first.decision is Decision.ALLOW
    assert first.packet == packet
    assert receiver.received == [packet]

    # The cached execution object is now stale even though its bytes are unchanged.
    gie.revoke(0)
    gie.grant(0, epoch=482)

    replay = path.commit(ATLExecutionObject(packet, epoch_1))
    receiver.transmit(replay.packet)

    assert replay.decision is Decision.BLOCK
    assert replay.reason == "authority_epoch_mismatch"
    assert replay.packet is None
    assert receiver.received == [packet]


def test_reference_path_enforces_safety_independently_of_authority():
    gie = GIE()
    epoch = gie.grant(0, epoch=481)
    path = GovernedExecutionPath(gie)
    packet = b"HALOS-ATL" + bytes(range(55))

    result = path.commit(
        ATLExecutionObject(packet, epoch),
        halos_decision=SafetyDecision.BLOCK,
        halos_reason="halos_unsafe",
    )

    assert result.decision is Decision.BLOCK
    assert result.reason == "safety_halos_unsafe"
    assert result.packet is None
