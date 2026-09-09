from poc.commit_gate import CommitGate, SafetyDecision, SafetyResult
from poc.gie import Decision, GIE
from poc.physical_boundary import (
    GovernedPhysicalPath,
    PhysicalExecutionObject,
    RecordingRelay,
)


def authorized_gie() -> GIE:
    gie = GIE()
    gie.grant(0)
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


def test_execution_identity_binds_authority_to_exact_payload():
    gie = authorized_gie()
    relay = RecordingRelay()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay)
    epoch = gie.current_epoch(0)
    authorized = PhysicalExecutionObject(0, b"RELAY:ON", epoch)
    mutated = PhysicalExecutionObject(0, b"RELAY:OFF", epoch)

    _, authority = path.prepare_authority(authorized)
    safety = SafetyResult(SafetyDecision.ALLOW, "halos_safe", mutated.action_digest)
    result = CommitGate().commit(0, mutated.action_digest, authority, safety)

    assert authority.action_digest != mutated.action_digest
    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_digest_mismatch"
    assert relay.applied_payloads == []


def test_cross_environment_command_never_reaches_actuator():
    gie = authorized_gie()
    gie.grant(1)
    relay = RecordingRelay()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay)
    execution = PhysicalExecutionObject(1, b"RELAY:ON", gie.current_epoch(1))

    result = path.commit(execution)

    assert result.decision is Decision.BLOCK
    assert result.reason == "execution_env_mismatch"
    assert result.applied is False
    assert relay.applied_payloads == []
