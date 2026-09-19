from __future__ import annotations

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


class EvidenceRecorder:
    """Append-only implementation evidence sink for the Magic Box PoC."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._records: list[CommitEvidence] = []
        self._lock = Lock()

    @property
    def records(self) -> tuple[CommitEvidence, ...]:
        with self._lock:
            return tuple(self._records)

    def record(self, evidence: CommitEvidence) -> None:
        line = json.dumps(asdict(evidence), sort_keys=True, separators=(",", ":"))
        with self._lock:
            self._records.append(evidence)
            if self._path is not None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
