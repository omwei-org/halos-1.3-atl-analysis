from poc.commit_gate import SafetyDecision
from poc.gie import Decision, GIE
from poc.physical_boundary import (
    GovernedPhysicalPath,
    PhysicalExecutionObject,
    RecordingRelay,
)


def authorized_gie() -> GIE:
    gie = GIE()
    gie.authorize(0)
    return gie


def test_allow_is_the_only_path_to_physical_io():
    gie = authorized_gie()
    relay = RecordingRelay()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay)
    execution = PhysicalExecutionObject(0, b"RELAY:ON", gie.current_epoch(0))

    result = path.commit(execution)

    assert result.decision is Decision.ALLOW
    assert result.applied is True
    assert relay.applied_payloads == [b"RELAY:ON"]
    assert relay.state is True


def test_authority_revoke_blocks_physical_effect():
    gie = authorized_gie()
    relay = RecordingRelay()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay)
    execution = PhysicalExecutionObject(0, b"RELAY:ON", gie.current_epoch(0))

    gie.revoke(0)
    result = path.commit(execution)

    assert result.decision is Decision.BLOCK
    assert result.applied is False
    assert relay.applied_payloads == []
    assert relay.state is False


def test_safety_block_prevents_physical_effect():
    gie = authorized_gie()
    relay = RecordingRelay()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay)
    execution = PhysicalExecutionObject(0, b"RELAY:ON", gie.current_epoch(0))

    result = path.commit(execution, SafetyDecision.BLOCK, "halos_blocked")

    assert result.decision is Decision.BLOCK
    assert result.applied is False
    assert relay.applied_payloads == []


def test_mutated_command_has_different_execution_identity():
    gie = authorized_gie()
    relay = RecordingRelay()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay)
    epoch = gie.current_epoch(0)
    authorized = PhysicalExecutionObject(0, b"RELAY:ON", epoch)
    mutated = PhysicalExecutionObject(0, b"RELAY:OFF", epoch)

    _, authority = path.prepare_authority(authorized)
    safety = path.commit(mutated)

    assert authority.action_digest != mutated.action_digest
    assert safety.decision is Decision.ALLOW
    assert safety.applied is True
    assert relay.applied_payloads == [b"RELAY:OFF"]


def test_cross_environment_command_never_reaches_actuator():
    gie = authorized_gie()
    gie.authorize(1)
    relay = RecordingRelay()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay)
    execution = PhysicalExecutionObject(1, b"RELAY:ON", gie.current_epoch(1))

    result = path.commit(execution)

    assert result.decision is Decision.BLOCK
    assert result.reason == "execution_env_mismatch"
    assert result.applied is False
    assert relay.applied_payloads == []
