from __future__ import annotations

import json
from pathlib import Path

from poc.evidence import EvidenceRecorder
from poc.gie import Decision, GIE
from poc.physical_boundary import GovernedPhysicalPath, PhysicalExecutionObject, RecordingRelay


def main() -> None:
    """Run 003: Control baseline (no revocation).

    Pair experiment to Run 002.
    - PREPARE @ epoch 1 → ALLOW
    - Authority remains valid (no revoke)
    - COMMIT @ epoch 1 → ALLOW
    - Physical effect applied
    """
    gie = GIE()
    epoch = gie.grant(0)
    relay = RecordingRelay()
    recorder = EvidenceRecorder("run-003-evidence.jsonl")
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay, evidence=recorder)

    command_id = "run003-control-001"
    execution = PhysicalExecutionObject(0, b"RELAY:ON", epoch)

    prepared = path.prepare(execution, command_id=command_id)
    # NO revocation here - authority remains valid
    result = path.commit_prepared(prepared)

    assert result.decision is Decision.ALLOW
    assert result.reason == "authorized"
    assert relay.applied_payloads == [b"RELAY:ON"]
    assert relay.state is True

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
