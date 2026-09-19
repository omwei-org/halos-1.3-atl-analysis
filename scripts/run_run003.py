from __future__ import annotations

import json
from pathlib import Path

from poc.evidence import EvidenceRecorder
from poc.gie import Decision
from poc.physical_boundary import GovernedPhysicalPath, PhysicalExecutionObject, RecordingRelay


def main() -> None:
    """Run 003: Control baseline.
    
    Verifies the successful path where:
    - Authority is granted
    - Action is prepared (ALLOW)
    - Authority is NOT revoked (remains valid)
    - Action is committed (ALLOW)
    - Physical effect is applied
    """
    relay = RecordingRelay()
    recorder = EvidenceRecorder()
    
    # Set up GIE authority without revocation
    from poc.gie import GIE
    gie = GIE()
    epoch = gie.grant(0)  # Grant authority at epoch 1
    
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay, evidence=recorder)

    command_id = "run003-control-001"
    execution = PhysicalExecutionObject(0, b"RELAY:ON", epoch)

    # PREPARE: Authority is ALLOW
    prepared = path.prepare(execution, command_id=command_id)
    assert prepared.authority.decision is Decision.ALLOW, "PREPARE should be ALLOW"
    
    # NO AUTHORITY CHANGE: epoch remains the same
    current_epoch_before_commit = gie.current_epoch(0)
    assert current_epoch_before_commit == epoch, "Authority epoch should not change"
    
    # COMMIT: Authority should still be ALLOW, physical effect applied
    result = path.commit_prepared(prepared)

    assert result.decision is Decision.ALLOW, "COMMIT should be ALLOW"
    assert result.reason == "authorized", "Reason should be authorized"
    assert result.applied is True, "Effect should be applied"
    assert relay.applied_payloads == [b"RELAY:ON"], "Payload should be applied to relay"
    assert relay.state is True, "Relay should be ON"

    records = [r.__dict__ for r in recorder.records]
    artifact = {
        "run": "003",
        "scenario": "control-baseline-no-revocation",
        "implementation": "GovernedPhysicalPath + GIE + RecordingRelay",
        "command_id": command_id,
        "initial_authority_epoch": epoch,
        "final_authority_epoch": gie.current_epoch(0),
        "result": {
            "decision": result.decision.value,
            "reason": result.reason,
            "applied": result.applied,
        },
        "records": records,
        "physical_effect": {
            "applied_payloads": [p.decode("utf-8") for p in relay.applied_payloads],
            "relay_state": relay.state,
        },
    }

    out = Path("run-003-evidence.json")
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
