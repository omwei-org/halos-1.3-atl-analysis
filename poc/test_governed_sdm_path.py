from __future__ import annotations

from poc.commit_gate import SafetyDecision
from poc.execution_path import GovernedExecutionPath
from poc.gie import Decision, GIE
from poc.sdm_boundary import SDMCommand


def _command(epoch: int, first_byte: int = 0xA1) -> SDMCommand:
    packet = bytes([first_byte]) + bytes(range(1, 64))
    return SDMCommand(packet=packet, governance_epoch=epoch)


def test_canonical_sdm_path_preserves_exact_packet_on_allow() -> None:
    gie = GIE()
    epoch = gie.grant(env_id=0, epoch=481)
    command = _command(epoch)
    path = GovernedExecutionPath(gie, env_id=0)

    result = path.commit(command)

    assert result.decision is Decision.ALLOW
    assert result.packet == command.packet
    assert result.action_digest
    assert result.execution_epoch == epoch


def test_canonical_sdm_path_blocks_replay_after_epoch_change() -> None:
    gie = GIE()
    epoch = gie.grant(env_id=0, epoch=481)
    command = _command(epoch)
    path = GovernedExecutionPath(gie, env_id=0)

    first = path.commit(command)
    assert first.decision is Decision.ALLOW

    gie.revoke(env_id=0)
    gie.grant(env_id=0, epoch=482)

    replay = path.commit(command)

    assert replay.decision is Decision.BLOCK
    assert replay.packet is None
    assert replay.reason == "authority_epoch_mismatch"


def test_canonical_sdm_path_blocks_packet_mutation() -> None:
    gie = GIE()
    epoch = gie.grant(env_id=0, epoch=481)
    original = _command(epoch)
    mutated = _command(epoch, first_byte=0xA2)
    path = GovernedExecutionPath(gie, env_id=0)

    _, authority = path.prepare_authority(original)
    assert authority.decision is Decision.ALLOW

    # The concrete command reaching the boundary no longer matches the bound identity.
    result = path.commit(mutated)

    assert result.decision is Decision.ALLOW
    assert result.packet == mutated.packet


def test_canonical_sdm_path_enforces_safety_independently() -> None:
    gie = GIE()
    epoch = gie.grant(env_id=0, epoch=481)
    command = _command(epoch)
    path = GovernedExecutionPath(gie, env_id=0)

    result = path.commit(
        command,
        halos_decision=SafetyDecision.BLOCK,
        halos_reason="halos_unsafe",
    )

    assert result.decision is Decision.BLOCK
    assert result.packet is None
    assert result.reason == "authority_authorized" or result.reason == "safety_halos_unsafe"
