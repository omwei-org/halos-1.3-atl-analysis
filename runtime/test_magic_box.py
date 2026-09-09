from __future__ import annotations

from poc.commit_gate import SafetyDecision
from runtime.commit_envelope import CommittedEnvelope
from runtime.magic_box import MagicBox


def test_authorized_command_reaches_actuator() -> None:
    box = MagicBox()
    epoch = box.authorize(0)

    result = box.execute(b"RELAY:ON", epoch, SafetyDecision.ALLOW)

    assert result["decision"] == "ALLOW"
    assert result["applied"] is True
    assert result["relay_state"] is True
    envelope = CommittedEnvelope.from_dict(result["committed_envelope"])
    assert envelope.commit_seq == 1
    assert envelope.governance_epoch == epoch
    assert envelope.target == "RELAY_1"
    assert envelope.state == "ON"
    assert envelope.action_digest == result["action_digest"]


def test_commit_sequence_is_monotonic() -> None:
    box = MagicBox()
    epoch = box.authorize(0)

    first = box.execute(b"RELAY:ON", epoch, SafetyDecision.ALLOW)
    second = box.execute(b"RELAY:OFF", epoch, SafetyDecision.ALLOW)

    assert first["committed_envelope"]["commit_seq"] == 1
    assert second["committed_envelope"]["commit_seq"] == 2


def test_revoke_blocks_while_controller_can_continue_sending() -> None:
    box = MagicBox()
    epoch = box.authorize(0)
    first = box.execute(b"RELAY:ON", epoch, SafetyDecision.ALLOW)
    assert first["applied"] is True

    box.revoke(0)

    blocked = box.execute(b"RELAY:OFF", epoch, SafetyDecision.ALLOW)

    assert blocked["decision"] == "BLOCK"
    assert blocked["applied"] is False
    assert blocked["relay_state"] is True
    assert blocked["committed_envelope"] is None


def test_safety_block_prevents_physical_effect() -> None:
    box = MagicBox()
    epoch = box.authorize(0)

    result = box.execute(b"RELAY:ON", epoch, SafetyDecision.BLOCK, "halos_block")

    assert result["decision"] == "BLOCK"
    assert result["applied"] is False
    assert result["relay_state"] is False
    assert result["committed_envelope"] is None


def test_stale_epoch_prevents_physical_effect() -> None:
    box = MagicBox()
    epoch = box.authorize(0)
    box.revoke(0)
    new_epoch = box.authorize(0)
    assert new_epoch != epoch

    result = box.execute(b"RELAY:ON", epoch, SafetyDecision.ALLOW)

    assert result["decision"] == "BLOCK"
    assert result["applied"] is False
    assert result["relay_state"] is False
    assert result["committed_envelope"] is None


def test_cross_environment_command_never_reaches_actuator() -> None:
    box = MagicBox()
    epoch = box.authorize(0)

    result = box.execute(b"RELAY:ON", epoch, SafetyDecision.ALLOW, env_id=1)

    assert result["decision"] == "BLOCK"
    assert result["applied"] is False
    assert result["relay_state"] is False
    assert result["committed_envelope"] is None
