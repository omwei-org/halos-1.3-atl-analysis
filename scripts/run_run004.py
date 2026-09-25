from __future__ import annotations

import json
from pathlib import Path

from poc.evidence import EvidenceRecorder
from poc.gie import Decision, GIE
from poc.physical_boundary import GovernedPhysicalPath, PhysicalExecutionObject, RecordingRelay


def run_case(
    *,
    command_id: str,
    commit_payload_factory=None,
) -> dict:
    gie = GIE()
    epoch = gie.grant(0)
    relay = RecordingRelay()
    recorder = EvidenceRecorder(Path(f"{command_id}.jsonl"))
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay, evidence=recorder)
    execution = PhysicalExecutionObject(0, b"RELAY:ON", epoch)

    result = path.commit(
        execution,
        commit_payload_factory=commit_payload_factory,
        command_id=command_id,
    )

    assert result.decision is Decision.ALLOW
    assert result.applied is True
    assert len(recorder.effect_records) == 1

    effect = recorder.effect_records[0]
    return {
        "command_id": command_id,
        "result": {
            "decision": result.decision.value,
            "reason": result.reason,
            "applied": result.applied,
        },
        "governed_action_digest": execution.action_digest,
        "effect_correlation": effect.__dict__,
        "physical_effect": {
            "applied_payloads": [p.decode("utf-8") for p in relay.applied_payloads],
            "relay_state": relay.state,
        },
    }


def main() -> None:
    nominal = run_case(command_id="run004-a-001")
    transformed = run_case(
        command_id="run004-b-001",
        commit_payload_factory=lambda payload, authority: b"RELAY:OFF",
    )

    assert nominal["effect_correlation"]["committed_action_digest"] == nominal["governed_action_digest"]
    assert nominal["effect_correlation"]["actuator_payload_digest"] == nominal["governed_action_digest"]

    assert transformed["effect_correlation"]["committed_action_digest"] == transformed["governed_action_digest"]
    assert transformed["effect_correlation"]["actuator_payload_digest"] != transformed["governed_action_digest"]

    artifact = {
        "run": "004",
        "scenario": "effect-correlation-and-transformation-detection",
        "implementation": "GovernedPhysicalPath + EvidenceRecorder + RecordingRelay",
        "cases": [nominal, transformed],
        "claims": [
            "Case A binds the governed action digest to the actuator payload digest in the PoC observation.",
            "Case B demonstrates that a post-gate payload transformation is visible as a digest mismatch.",
            "The RecordingRelay observation is a PoC adapter observation, not physical-world attestation.",
        ],
    }

    out = Path("run-004-evidence.json")
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
