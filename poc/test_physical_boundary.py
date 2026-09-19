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
    assert result.reason == "authority_STALE_EPOCH"
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


def test_run002_revocation_persists_stage_correlation():
    from poc.evidence import EvidenceRecorder

    gie = authorized_gie()
    relay = RecordingRelay()
    recorder = EvidenceRecorder()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay, evidence=recorder)
    epoch = gie.current_epoch(0)
    command_id = "run002-revoke-001"
    execution = PhysicalExecutionObject(0, b"RELAY:ON", epoch)

    prepared = path.prepare(execution, command_id=command_id)
    gie.revoke(0)
    result = path.commit_prepared(prepared)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_STALE_EPOCH"
    assert result.applied is False
    assert relay.applied_payloads == []

    records = recorder.records
    assert [r.stage for r in records] == ["PREPARE", "FINAL_AUTHORITY_CHECK", "COMMIT"]
    assert all(r.command_id == command_id for r in records)
    assert all(r.action_digest == execution.action_digest for r in records)
    assert records[0].authority_epoch == epoch
    assert records[1].authority_epoch == epoch + 1
    assert records[1].authorization_decision == "BLOCK"
    assert records[1].authorization_reason == "STALE_EPOCH"
    assert records[2].execution_outcome == "NOT_ATTEMPTED"


def test_run002_control_no_authority_change_allows_and_persists():
    from poc.evidence import EvidenceRecorder

    gie = authorized_gie()
    relay = RecordingRelay()
    recorder = EvidenceRecorder()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay, evidence=recorder)
    epoch = gie.current_epoch(0)
    command_id = "run002-control-001"
    execution = PhysicalExecutionObject(0, b"RELAY:ON", epoch)

    result = path.commit(execution, command_id=command_id)

    assert result.decision is Decision.ALLOW
    assert result.applied is True
    records = recorder.records
    assert [r.stage for r in records] == ["PREPARE", "FINAL_AUTHORITY_CHECK", "EXECUTION"]
    assert all(r.command_id == command_id for r in records)
    assert all(r.action_digest == execution.action_digest for r in records)
    assert all(r.authority_epoch == epoch for r in records)
    assert records[-1].execution_outcome == "COMMITTED"


def test_auto_command_id_is_shared_by_result_and_evidence():
    from poc.evidence import EvidenceRecorder

    gie = authorized_gie()
    relay = RecordingRelay()
    recorder = EvidenceRecorder()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay, evidence=recorder)
    execution = PhysicalExecutionObject(0, b"RELAY:ON", gie.current_epoch(0))

    result = path.commit(execution)

    assert result.decision is Decision.ALLOW
    assert result.command_id is not None
    assert all(r.command_id == result.command_id for r in recorder.records)
