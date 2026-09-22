from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class CommitEvidence:
    stage: str
    command_id: str
    env_id: int
    action_digest: str
    execution_epoch: int
    authority_epoch: int
    authorization_decision: str
    authorization_reason: str
    safety_decision: str | None
    safety_reason: str | None
    commit_decision: str | None
    commit_reason: str | None
    execution_outcome: str | None
    applied: bool
    timestamp: str
    prev_hash: str
    record_hash: str


class EvidenceRecorder:
    """Append-only implementation evidence sink for the Magic Box PoC.

    Evidence recording is mandatory: a path must be provided at initialization.
    Each record is integrity-protected via a hash chain linking to the previous record.
    """

    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    # Fixed field order for hash computation (excluding prev_hash and record_hash)
    _HASH_FIELD_ORDER = [
        "stage",
        "command_id",
        "env_id",
        "action_digest",
        "execution_epoch",
        "authority_epoch",
        "authorization_decision",
        "authorization_reason",
        "safety_decision",
        "safety_reason",
        "commit_decision",
        "commit_reason",
        "execution_outcome",
        "applied",
        "timestamp",
    ]

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._records: list[CommitEvidence] = []
        self._lock = Lock()
        self._last_hash = self.GENESIS_HASH

    @property
    def records(self) -> tuple[CommitEvidence, ...]:
        with self._lock:
            return tuple(self._records)

    def _compute_record_hash(self, evidence_dict: dict, prev_hash: str) -> str:
        """Compute record_hash = SHA256(prev_hash + serialized_evidence_fields)."""
        # Extract fields in fixed order, excluding hash fields
        hash_input = prev_hash
        for field in self._HASH_FIELD_ORDER:
            value = evidence_dict[field]
            # Serialize each field value as compact JSON
            field_json = json.dumps(value, separators=(",", ":"))
            hash_input += field_json
        return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

    def record(self, evidence: CommitEvidence) -> None:
        """Record evidence with hash-chain integrity protection."""
        evidence_dict = asdict(evidence)

        # Remove hash fields if present (shouldn't be, but defensive)
        evidence_dict.pop("prev_hash", None)
        evidence_dict.pop("record_hash", None)

        with self._lock:
            # Compute hash chain
            prev_hash = self._last_hash
            record_hash = self._compute_record_hash(evidence_dict, prev_hash)

            # Add hash fields to the record
            evidence_dict["prev_hash"] = prev_hash
            evidence_dict["record_hash"] = record_hash

            # Reconstruct CommitEvidence with hashes
            evidence_with_hashes = CommitEvidence(**evidence_dict)

            # Serialize for persistence
            line = json.dumps(evidence_dict, sort_keys=True, separators=(",", ":"))

            # Persist to disk
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

            # Update in-memory state
            self._records.append(evidence_with_hashes)
            self._last_hash = record_hash

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
