from __future__ import annotations

from poc.atl_boundary import ATLExecutionObject
from poc.commit_gate import SafetyDecision
from poc.execution_path import GovernedExecutionPath
from poc.gie import Decision, GIE


class MockATLReceiver:
    def __init__(self) -> None:
        self.received: list[bytes] = []

    def transmit(self, payload: bytes | None) -> None:
        if payload is not None:
            self.received.append(payload)


def test_reference_path_blocks_stale_execution_after_authority_change():
    gie = GIE()
    epoch_1 = gie.grant(0, epoch=481)
    path = GovernedExecutionPath(gie, env_id=0)
    receiver = MockATLReceiver()
    packet = bytes(range(64))

    first = path.commit(ATLExecutionObject(packet, epoch_1))
    receiver.transmit(first.packet)

    assert first.decision is Decision.ALLOW
    assert first.packet == packet
    assert receiver.received == [packet]

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
    path = GovernedExecutionPath(gie, env_id=0)
    packet = b"HALOS-ATL" + bytes(range(55))

    result = path.commit(
        ATLExecutionObject(packet, epoch),
        halos_decision=SafetyDecision.BLOCK,
        halos_reason="halos_unsafe",
    )

    assert result.decision is Decision.BLOCK
    assert result.reason == "safety_halos_unsafe"
    assert result.packet is None


def test_authority_isolated_per_execution_environment():
    gie = GIE()
    gie.grant(0, epoch=481)
    gie.grant(1, epoch=731)
    path_0 = GovernedExecutionPath(gie, env_id=0)
    path_1 = GovernedExecutionPath(gie, env_id=1)
    packet = b"HALOS-ATL" + bytes(range(55))

    assert path_0.commit(ATLExecutionObject(packet, 481)).decision is Decision.ALLOW
    assert path_1.commit(ATLExecutionObject(packet, 731)).decision is Decision.ALLOW

    gie.revoke(0)

    blocked = path_0.commit(ATLExecutionObject(packet, 481))
    still_allowed = path_1.commit(ATLExecutionObject(packet, 731))

    assert blocked.decision is Decision.BLOCK
    assert still_allowed.decision is Decision.ALLOW
