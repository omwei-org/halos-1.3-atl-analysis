from __future__ import annotations

from poc.atl_boundary import ATLCommitBoundary
from poc.commit_gate import CommitGate, SafetyDecision
from poc.gie import Decision, GIE, make_bytes_execution_evidence
from poc.halos_adapter import HalosAdapter
from poc.sdm_boundary import SDMCommand, SDMCommitAdapter


class MockATLReceiver:
    def __init__(self) -> None:
        self.received: list[bytes] = []

    def transmit(self, payload: bytes | None) -> None:
        if payload is not None:
            self.received.append(payload)


def test_sdm_allowed_packet_reaches_receiver_byte_for_byte():
    gie = GIE()
    epoch = gie.grant(0, epoch=481)
    packet = b"HALOS-ATL" + bytes(range(55))
    command = SDMCommand(packet=packet, governance_epoch=epoch)
    boundary = ATLCommitBoundary(CommitGate())
    adapter = SDMCommitAdapter(boundary)
    receiver = MockATLReceiver()

    evidence = make_bytes_execution_evidence(0, packet, epoch)
    authority = gie.check_bytes_evidence(evidence, packet)
    safety = HalosAdapter.bind(evidence.action_digest, SafetyDecision.ALLOW, "halos_safe")

    result = adapter.commit(command, authority, safety)
    receiver.transmit(adapter.transmit_payload(command, result))

    assert result.decision is Decision.ALLOW
    assert receiver.received == [packet]
    assert receiver.received[0] == packet


def test_sdm_replay_after_reauthorization_is_blocked():
    gie = GIE()
    epoch_481 = gie.grant(0, epoch=481)
    packet = bytes(range(64))
    command = SDMCommand(packet=packet, governance_epoch=epoch_481)
    boundary = ATLCommitBoundary(CommitGate())
    adapter = SDMCommitAdapter(boundary)
    receiver = MockATLReceiver()

    evidence_481 = make_bytes_execution_evidence(0, packet, epoch_481)
    authority_481 = gie.check_bytes_evidence(evidence_481, packet)
    safety_481 = HalosAdapter.bind(evidence_481.action_digest, SafetyDecision.ALLOW, "halos_safe")
    first = adapter.commit(command, authority_481, safety_481)
    receiver.transmit(adapter.transmit_payload(command, first))
    assert first.decision is Decision.ALLOW

    gie.revoke(0)
    gie.grant(0, epoch=482)

    stale_evidence = make_bytes_execution_evidence(0, packet, epoch_481)
    stale_authority = gie.check_bytes_evidence(stale_evidence, packet)
    stale_safety = HalosAdapter.bind(stale_evidence.action_digest, SafetyDecision.ALLOW, "halos_safe")
    replay = adapter.commit(command, stale_authority, stale_safety)
    receiver.transmit(adapter.transmit_payload(command, replay))

    assert replay.decision is Decision.BLOCK
    assert replay.reason == "authority_epoch_mismatch"
    assert receiver.received == [packet]


def test_sdm_packet_mutation_after_authority_binding_is_blocked():
    gie = GIE()
    epoch = gie.grant(0, epoch=481)
    original = bytes(range(64))
    mutated = bytes([255]) + original[1:]
    boundary = ATLCommitBoundary(CommitGate())
    adapter = SDMCommitAdapter(boundary)

    evidence = make_bytes_execution_evidence(0, original, epoch)
    authority = gie.check_bytes_evidence(evidence, original)
    safety = HalosAdapter.bind(evidence.action_digest, SafetyDecision.ALLOW, "halos_safe")

    mutated_command = SDMCommand(packet=mutated, governance_epoch=epoch)
    result = adapter.commit(mutated_command, authority, safety)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_digest_mismatch"
    assert adapter.transmit_payload(mutated_command, result) is None
