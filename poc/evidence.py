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


@dataclass(frozen=True)
class EffectCorrelationEvidence:
    """Integrity-protected binding between a committed action and an observation."""

    stage: str
    command_id: str
    env_id: int
    committed_action_digest: str
    actuator_payload_digest: str
    effect_digest: str
    effect_status: str
    observed_at: str
    effect_source: str
    prev_hash: str
    record_hash: str


class EvidenceRecorder:
    """Append-only implementation evidence sink for the Magic Box PoC.

    Evidence recording is mandatory: a path must be provided at initialization.
    Commit and effect-correlation records share one append-only SHA-256 hash chain.
    """

    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    _HASH_FIELD_ORDER = [
        "stage", "command_id", "env_id", "action_digest", "execution_epoch",
        "authority_epoch", "authorization_decision", "authorization_reason",
        "safety_decision", "safety_reason", "commit_decision", "commit_reason",
        "execution_outcome", "applied", "timestamp",
    ]

    _EFFECT_HASH_FIELD_ORDER = [
        "stage", "command_id", "env_id", "committed_action_digest",
        "actuator_payload_digest", "effect_digest", "effect_status",
        "observed_at", "effect_source",
    ]

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._records: list[CommitEvidence] = []
        self._effect_records: list[EffectCorrelationEvidence] = []
        self._lock = Lock()
        self._last_hash = self.GENESIS_HASH

    @property
    def records(self) -> tuple[CommitEvidence, ...]:
        with self._lock:
            return tuple(self._records)

    @property
    def effect_records(self) -> tuple[EffectCorrelationEvidence, ...]:
        with self._lock:
            return tuple(self._effect_records)

    def _compute_hash(self, evidence_dict: dict, prev_hash: str, fields: list[str]) -> str:
        hash_input = prev_hash
        for field in fields:
            hash_input += json.dumps(evidence_dict[field], separators=(",", ":"))
        return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

    def _append_record(self, evidence_dict: dict, fields: list[str]) -> tuple[str, str]:
        with self._lock:
            prev_hash = self._last_hash
            record_hash = self._compute_hash(evidence_dict, prev_hash, fields)
            evidence_dict["prev_hash"] = prev_hash
            evidence_dict["record_hash"] = record_hash
            line = json.dumps(evidence_dict, sort_keys=True, separators=(",", ":"))
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            self._last_hash = record_hash
            return prev_hash, record_hash

    def record(self, evidence: CommitEvidence) -> None:
        """Record a CommitEvidence item with hash-chain integrity protection."""
        evidence_dict = asdict(evidence)
        evidence_dict.pop("prev_hash", None)
        evidence_dict.pop("record_hash", None)
        self._append_record(evidence_dict, self._HASH_FIELD_ORDER)
        self._records.append(CommitEvidence(**evidence_dict))

    def record_effect_correlation(self, evidence: EffectCorrelationEvidence) -> None:
        """Record an effect-correlation item on the same integrity chain."""
        evidence_dict = asdict(evidence)
        evidence_dict.pop("prev_hash", None)
        evidence_dict.pop("record_hash", None)
        record_dict = dict(evidence_dict)
        record_dict["record_type"] = "EFFECT_CORRELATION"
        self._append_record(record_dict, self._EFFECT_HASH_FIELD_ORDER)
        self._effect_records.append(EffectCorrelationEvidence(
            **{key: record_dict[key] for key in asdict(evidence).keys()}
        ))

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
