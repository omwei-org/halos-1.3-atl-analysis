from __future__ import annotations

import json
from pathlib import Path

from poc.evidence import EvidenceRecorder
from poc.gie import Decision, GIE
from poc.physical_boundary import GovernedPhysicalPath, PhysicalExecutionObject, RecordingRelay


def main() -> None:
    gie = GIE()
    epoch = gie.grant(0)
    relay = RecordingRelay()
    recorder = EvidenceRecorder()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay, evidence=recorder)

    command_id = "run002-revoke-001"
    execution = PhysicalExecutionObject(0, b"RELAY:ON", epoch)

    prepared = path.prepare(execution, command_id=command_id)
    gie.revoke(0)
    result = path.commit_prepared(prepared)

    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_STALE_EPOCH"
    assert relay.applied_payloads == []

    records = [r.__dict__ for r in recorder.records]
    artifact = {
        "run": "002",
        "scenario": "prepare-authorize-revoke-before-commit",
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

    out = Path("run-002-evidence.json")
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
