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
    assert result.reason == "safety_halos_unsafe"


def test_canonical_sdm_path_isolated_by_environment() -> None:
    gie = GIE()
    epoch_0 = gie.grant(env_id=0, epoch=481)
    epoch_1 = gie.grant(env_id=1, epoch=731)
    command_0 = _command(epoch_0)
    command_1 = _command(epoch_1, first_byte=0xB2)
    path_0 = GovernedExecutionPath(gie, env_id=0)
    path_1 = GovernedExecutionPath(gie, env_id=1)

    allowed_0 = path_0.commit(command_0)
    allowed_1 = path_1.commit(command_1)
    assert allowed_0.decision is Decision.ALLOW
    assert allowed_1.decision is Decision.ALLOW

    gie.revoke(env_id=0)

    blocked_0 = path_0.commit(command_0)
    still_allowed_1 = path_1.commit(command_1)

    assert blocked_0.decision is Decision.BLOCK
    assert blocked_0.packet is None
    assert still_allowed_1.decision is Decision.ALLOW
    assert still_allowed_1.packet == command_1.packet
