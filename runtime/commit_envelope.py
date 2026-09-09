from __future__ import annotations

import json
from dataclasses import dataclass, fields

REQUIRED_FIELDS: tuple[str, ...] = (
    "version",
    "command_id",
    "target",
    "state",
    "commit_seq",
    "action_digest",
    "governance_epoch",
)


@dataclass(frozen=True)
class CommittedEnvelope:
    """The canonical execution envelope sent from Commit Gate to Actuation.

    This is the exact, locked v1 contract: identity and commit-time evidence
    only. It intentionally carries no IPC authentication/MAC field -- post-
    commit transport integrity (Claim B) is an explicitly open, documented
    gap in v1, not something this envelope is meant to close.
    """

    version: int
    command_id: str
    target: str
    state: str
    commit_seq: int
    action_digest: str
    governance_epoch: int

    def to_dict(self) -> dict[str, object]:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CommittedEnvelope":
        keys = set(data)
        required = set(REQUIRED_FIELDS)
        missing = required - keys
        extra = keys - required
        if missing:
            raise ValueError(f"committed envelope missing required fields: {sorted(missing)}")
        if extra:
            raise ValueError(f"committed envelope has fields outside the locked contract: {sorted(extra)}")
        return cls(**data)  # type: ignore[arg-type]


def encode_envelope(envelope: CommittedEnvelope) -> str:
    """Serialize a committed envelope to JSON with exactly the contract fields."""
    return json.dumps(envelope.to_dict())
