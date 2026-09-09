from __future__ import annotations

import inspect
import json

import pytest

from runtime.adapters.unix_socket_actuator import UnixSocketActuator
from runtime.commit_envelope import CommittedEnvelope, REQUIRED_FIELDS, encode_envelope


EXPECTED_FIELDS = {
    "version",
    "command_id",
    "target",
    "state",
    "commit_seq",
    "action_digest",
    "governance_epoch",
}


def make_envelope(**overrides: object) -> CommittedEnvelope:
    values = {
        "version": 1,
        "command_id": "cmd-0001",
        "target": "RELAY_1",
        "state": "ON",
        "commit_seq": 42,
        "action_digest": "a" * 64,
        "governance_epoch": 7,
    }
    values.update(overrides)
    return CommittedEnvelope(**values)


def test_committed_envelope_has_exact_contract_fields() -> None:
    assert set(REQUIRED_FIELDS) == EXPECTED_FIELDS
    envelope = make_envelope()
    assert set(envelope.to_dict()) == EXPECTED_FIELDS


def test_committed_envelope_is_json_serializable_with_exact_fields() -> None:
    encoded = encode_envelope(make_envelope())
    decoded = json.loads(encoded)
    assert set(decoded) == EXPECTED_FIELDS
    assert decoded["version"] == 1
    assert decoded["command_id"] == "cmd-0001"
    assert decoded["target"] == "RELAY_1"
    assert decoded["state"] == "ON"
    assert decoded["commit_seq"] == 42
    assert decoded["action_digest"] == "a" * 64
    assert decoded["governance_epoch"] == 7


def test_committed_envelope_rejects_missing_or_extra_fields() -> None:
    data = make_envelope().to_dict()
    data.pop("action_digest")
    with pytest.raises(ValueError):
        CommittedEnvelope.from_dict(data)

    data = make_envelope().to_dict()
    data["unexpected"] = "must-not-cross-contract"
    with pytest.raises(ValueError):
        CommittedEnvelope.from_dict(data)


def test_actuation_adapter_has_no_governance_or_safety_dependency() -> None:
    source = inspect.getsource(UnixSocketActuator)
    forbidden = (
        "GIE",
        "CommitGate",
        "SafetyDecision",
        "SafetyResult",
        "authority",
        "halos",
    )
    assert not any(term in source for term in forbidden)


def test_actuation_adapter_is_only_a_transport_adapter() -> None:
    signature = inspect.signature(UnixSocketActuator.apply)
    parameters = list(signature.parameters.values())
    assert [parameter.name for parameter in parameters] == ["self", "payload"]
    assert parameters[1].annotation in (bytes, "bytes")


def test_post_commit_ipc_integrity_is_explicitly_out_of_scope_v1() -> None:
    """The v1 contract records identity; it does not make IPC trusted."""
    envelope = make_envelope()
    assert "action_digest" in envelope.to_dict()
    assert "commit_seq" in envelope.to_dict()
    # The contract intentionally defines no IPC authentication/MAC field.
    assert "ipc_mac" not in envelope.to_dict()
    assert "transport_signature" not in envelope.to_dict()
