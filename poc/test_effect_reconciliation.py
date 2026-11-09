"""Crash/reconciliation tests with independent downstream effect accounting.

T3 uses a real child-process termination (os._exit) after a separately committed
SQLite downstream effect and before the local outcome is finalized. Both SQLite
databases are software models; neither is evidence about a physical actuator.

T4 makes the downstream reconciliation contract explicit. A retry is permitted
only after an authoritative ABSENT observation; APPLIED suppresses retry and
UNKNOWN remains blocked.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol


class ReconciliationStatus(Enum):
    APPLIED = "APPLIED"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DownstreamObservation:
    status: ReconciliationStatus
    payloads: tuple[bytes, ...] = ()
    authoritative: bool = False


class DownstreamReconciliation(Protocol):
    """Contract required before recovery may retry an ambiguous operation.

    Implementations must scope lookup to the stable command/effect identity and
    return:
      * APPLIED only when the effect is authoritatively known to have occurred;
      * ABSENT only when the lookup is authoritative and complete enough to
        establish that no matching effect occurred;
      * UNKNOWN whenever visibility, retention, consistency, or identity is
        insufficient to decide.

    APPLIED and ABSENT must carry authoritative=True. A non-authoritative
    observation is treated as UNKNOWN regardless of its claimed status.

    ABSENT must not be inferred from a timeout, transport error, stale replica,
    incomplete query, or missing telemetry. The lookup must cover every path by
    which this command could have caused the Protected Effect. The implementation
    must document its consistency and retention guarantees. This test contract
    does not itself establish that a real downstream system satisfies them.
    """

    def lookup(self, command_id: str) -> DownstreamObservation: ...


@dataclass
class DownstreamEffectSink:
    """Independent in-memory observer/actuator model used by focused tests."""

    effects: list[tuple[str, bytes]] = field(default_factory=list)
    invocation_count: int = 0

    def apply(self, command_id: str, payload: bytes) -> None:
        self.invocation_count += 1
        self.effects.append((command_id, payload))

    def find(self, command_id: str) -> list[tuple[str, bytes]]:
        return [effect for effect in self.effects if effect[0] == command_id]

    def lookup(self, command_id: str) -> DownstreamObservation:
        found = self.find(command_id)
        return DownstreamObservation(
            ReconciliationStatus.APPLIED if found else ReconciliationStatus.ABSENT,
            tuple(payload for _, payload in found),
            authoritative=True,
        )

    @property
    def effect_count(self) -> int:
        return len(self.effects)


class SQLiteDownstreamEffectSink:
    """Durable process-independent software sink, separate from the local journal."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._db = sqlite3.connect(self.path)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS effects (
                effect_id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_id TEXT NOT NULL,
                payload BLOB NOT NULL
            )"""
        )
        self._db.commit()

    def apply(self, command_id: str, payload: bytes) -> None:
        self._db.execute(
            "INSERT INTO effects(command_id, payload) VALUES (?, ?)",
            (command_id, payload),
        )
        self._db.commit()

    def lookup(self, command_id: str) -> DownstreamObservation:
        rows = self._db.execute(
            "SELECT payload FROM effects WHERE command_id = ? ORDER BY effect_id",
            (command_id,),
        ).fetchall()
        payloads = tuple(bytes(row[0]) for row in rows)
        return DownstreamObservation(
            ReconciliationStatus.APPLIED if payloads else ReconciliationStatus.ABSENT,
            payloads,
            authoritative=True,
        )

    @property
    def effect_count(self) -> int:
        row = self._db.execute("SELECT COUNT(*) FROM effects").fetchone()
        return int(row[0])

    def close(self) -> None:
        self._db.close()


class LocalOperationStore:
    """SQLite-backed local outcome journal, separate from downstream effects."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._db = sqlite3.connect(self.path)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS operations (
                command_id TEXT PRIMARY KEY,
                outcome TEXT NOT NULL
            )"""
        )
        self._db.commit()

    def record(self, command_id: str, outcome: str) -> None:
        self._db.execute(
            """INSERT INTO operations(command_id, outcome) VALUES (?, ?)
               ON CONFLICT(command_id) DO UPDATE SET outcome=excluded.outcome""",
            (command_id, outcome),
        )
        self._db.commit()

    def outcome(self, command_id: str) -> str | None:
        row = self._db.execute(
            "SELECT outcome FROM operations WHERE command_id = ?", (command_id,)
        ).fetchone()
        return row[0] if row else None

    def mark_interrupted_unknown(self) -> None:
        self._db.execute(
            "UPDATE operations SET outcome='UNKNOWN' WHERE outcome='IN_PROGRESS'"
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()


def _crash_worker(
    journal_path: str,
    sink_path: str,
    command_id: str,
    payload: bytes,
    exit_code: int = 73,
) -> None:
    """Child process: persist intent, commit effect, then terminate without cleanup."""
    local = LocalOperationStore(journal_path)
    local.record(command_id, "IN_PROGRESS")
    sink = SQLiteDownstreamEffectSink(sink_path)
    sink.apply(command_id, payload)
    # Deliberately bypass finally blocks, Python teardown, and normal process exit.
    # The OS closes descriptors; SQLite's committed transactions must survive.
    os._exit(exit_code)


def execute_with_subprocess_crash(
    command_id: str,
    payload: bytes,
    journal_path: Path,
    sink_path: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the effect in a separate interpreter and require abrupt termination."""
    code = (
        "from poc.test_effect_reconciliation import _crash_worker; "
        "import sys; "
        "_crash_worker(sys.argv[1], sys.argv[2], sys.argv[3], "
        "bytes.fromhex(sys.argv[4]), int(sys.argv[5]))"
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(journal_path),
            str(sink_path),
            command_id,
            payload.hex(),
            "73",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )


def recover_before_retry(
    command_id: str,
    payload: bytes,
    sink: DownstreamReconciliation,
    local: LocalOperationStore,
) -> str:
    """Reconcile authoritative downstream state before any retry."""
    local.mark_interrupted_unknown()
    observed = sink.lookup(command_id)

    if (
        observed.status is ReconciliationStatus.UNKNOWN
        or not observed.authoritative
    ):
        # An inconclusive or non-authoritative lookup cannot authorize an effect.
        local.record(command_id, "UNKNOWN")
        return "BLOCKED_DOWNSTREAM_STATE_UNKNOWN"

    if observed.status is ReconciliationStatus.APPLIED:
        if len(observed.payloads) != 1:
            raise AssertionError("expected exactly one effect for stable command_id")
        if observed.payloads[0] != payload:
            raise AssertionError("command_id collision or downstream payload mismatch")
        local.record(command_id, "SUCCEEDED")
        return "RECONCILED_ALREADY_APPLIED"

    if observed.status is not ReconciliationStatus.ABSENT:
        raise AssertionError(f"unsupported reconciliation status: {observed.status}")

    # ABSENT authorizes retry only under the explicit lookup contract above.
    local.record(command_id, "RETRY_AUTHORIZED")
    try:
        sink.apply(command_id, payload)  # type: ignore[attr-defined]
    except Exception:
        # The apply call itself may have crossed the effect boundary before failing.
        # Never interpret its exception as proof of absence; reconcile again.
        local.record(command_id, "UNKNOWN")
        return "RETRY_OUTCOME_UNKNOWN"
    local.record(command_id, "SUCCEEDED")
    return "RETRIED_AFTER_CONFIRMED_ABSENCE"


def test_crash_after_effect_recovers_persisted_outcome_as_unknown(tmp_path):
    journal_path = tmp_path / "operations.sqlite"
    sink_path = tmp_path / "downstream.sqlite"
    command_id = "subprocess-crash-001"

    child = execute_with_subprocess_crash(
        command_id, b"RELAY:ON", journal_path, sink_path
    )
    assert child.returncode == 73, child.stderr

    # Parent opens the two independent stores only after the child has died.
    local = LocalOperationStore(journal_path)
    sink = SQLiteDownstreamEffectSink(sink_path)
    assert local.outcome(command_id) == "IN_PROGRESS"
    observed = sink.lookup(command_id)
    assert observed.status is ReconciliationStatus.APPLIED
    assert observed.payloads == (b"RELAY:ON",)
    assert sink.effect_count == 1

    # Recovery converts the durable in-flight marker to UNKNOWN.
    local.mark_interrupted_unknown()
    assert local.outcome(command_id) == "UNKNOWN"
    local.close()
    sink.close()


def test_recovery_reconciles_before_retry_and_prevents_duplicate_effect(tmp_path):
    journal_path = tmp_path / "operations.sqlite"
    sink_path = tmp_path / "downstream.sqlite"
    command_id = "subprocess-reconcile-002"

    child = execute_with_subprocess_crash(
        command_id, b"RELAY:ON", journal_path, sink_path
    )
    assert child.returncode == 73, child.stderr

    restarted_local = LocalOperationStore(journal_path)
    restarted_sink = SQLiteDownstreamEffectSink(sink_path)
    assert restarted_local.outcome(command_id) == "IN_PROGRESS"

    result = recover_before_retry(
        command_id, b"RELAY:ON", restarted_sink, restarted_local
    )

    assert result == "RECONCILED_ALREADY_APPLIED"
    assert restarted_local.outcome(command_id) == "SUCCEEDED"
    assert restarted_sink.effect_count == 1
    assert restarted_sink.lookup(command_id).payloads == (b"RELAY:ON",)
    restarted_local.close()
    restarted_sink.close()


def test_recovery_retries_only_after_authoritative_absence(tmp_path):
    sink = DownstreamEffectSink()
    local = LocalOperationStore(tmp_path / "operations.sqlite")
    command_id = "not-applied-003"

    local.record(command_id, "UNKNOWN")
    result = recover_before_retry(command_id, b"RELAY:ON", sink, local)

    assert result == "RETRIED_AFTER_CONFIRMED_ABSENCE"
    assert local.outcome(command_id) == "SUCCEEDED"
    assert sink.effect_count == 1
    assert sink.invocation_count == 1
    assert sink.find(command_id) == [(command_id, b"RELAY:ON")]
    local.close()


def test_recovery_does_not_retry_when_downstream_lookup_is_unknown(tmp_path):
    class UnavailableDownstream:
        def lookup(self, command_id: str) -> DownstreamObservation:
            return DownstreamObservation(ReconciliationStatus.UNKNOWN, authoritative=False)

        def apply(self, command_id: str, payload: bytes) -> None:
            raise AssertionError("UNKNOWN lookup must never authorize an effect")

    local = LocalOperationStore(tmp_path / "operations.sqlite")
    command_id = "lookup-unknown-004"
    local.record(command_id, "IN_PROGRESS")

    result = recover_before_retry(
        command_id, b"RELAY:ON", UnavailableDownstream(), local
    )

    assert result == "BLOCKED_DOWNSTREAM_STATE_UNKNOWN"
    assert local.outcome(command_id) == "UNKNOWN"
    local.close()


def test_duplicate_downstream_effect_is_visible_to_independent_counter():
    sink = DownstreamEffectSink()
    command_id = "duplicate-005"

    sink.apply(command_id, b"RELAY:ON")
    sink.apply(command_id, b"RELAY:ON")

    # The sink intentionally has no idempotency behavior: it exposes duplicates.
    assert sink.invocation_count == 2
    assert sink.effect_count == 2
    assert len(sink.find(command_id)) == 2



def test_non_authoritative_absence_never_authorizes_retry(tmp_path):
    class StaleReplica:
        def __init__(self):
            self.apply_calls = 0

        def lookup(self, command_id: str) -> DownstreamObservation:
            # A stale/incomplete view claims ABSENT but cannot establish it.
            return DownstreamObservation(
                ReconciliationStatus.ABSENT, authoritative=False
            )

        def apply(self, command_id: str, payload: bytes) -> None:
            self.apply_calls += 1

    sink = StaleReplica()
    local = LocalOperationStore(tmp_path / "operations.sqlite")
    command_id = "stale-absence-006"
    local.record(command_id, "IN_PROGRESS")

    result = recover_before_retry(command_id, b"RELAY:ON", sink, local)

    assert result == "BLOCKED_DOWNSTREAM_STATE_UNKNOWN"
    assert local.outcome(command_id) == "UNKNOWN"
    assert sink.apply_calls == 0
    local.close()


def test_non_authoritative_applied_observation_does_not_finalize_success(tmp_path):
    class IncompleteObserver:
        def lookup(self, command_id: str) -> DownstreamObservation:
            return DownstreamObservation(
                ReconciliationStatus.APPLIED,
                (b"RELAY:ON",),
                authoritative=False,
            )

        def apply(self, command_id: str, payload: bytes) -> None:
            raise AssertionError("non-authoritative observation must not trigger retry")

    local = LocalOperationStore(tmp_path / "operations.sqlite")
    command_id = "incomplete-applied-007"
    local.record(command_id, "IN_PROGRESS")

    result = recover_before_retry(
        command_id, b"RELAY:ON", IncompleteObserver(), local
    )

    assert result == "BLOCKED_DOWNSTREAM_STATE_UNKNOWN"
    assert local.outcome(command_id) == "UNKNOWN"
    local.close()


def test_duplicate_applied_records_are_not_silently_reconciled(tmp_path):
    sink = DownstreamEffectSink()
    local = LocalOperationStore(tmp_path / "operations.sqlite")
    command_id = "duplicate-reconcile-008"
    sink.apply(command_id, b"RELAY:ON")
    sink.apply(command_id, b"RELAY:ON")
    local.record(command_id, "IN_PROGRESS")

    try:
        recover_before_retry(command_id, b"RELAY:ON", sink, local)
    except AssertionError as exc:
        assert "exactly one effect" in str(exc)
    else:
        raise AssertionError("duplicate effects must not be reconciled as one success")

    assert local.outcome(command_id) == "UNKNOWN"
    assert sink.effect_count == 2
    local.close()


def test_repeated_recovery_after_applied_effect_does_not_duplicate(tmp_path):
    sink = DownstreamEffectSink()
    local = LocalOperationStore(tmp_path / "operations.sqlite")
    command_id = "repeat-recovery-009"
    sink.apply(command_id, b"RELAY:ON")
    local.record(command_id, "IN_PROGRESS")

    first = recover_before_retry(command_id, b"RELAY:ON", sink, local)
    second = recover_before_retry(command_id, b"RELAY:ON", sink, local)

    assert first == "RECONCILED_ALREADY_APPLIED"
    assert second == "RECONCILED_ALREADY_APPLIED"
    assert local.outcome(command_id) == "SUCCEEDED"
    assert sink.effect_count == 1
    assert sink.invocation_count == 1
    local.close()



def test_retry_exception_after_effect_is_reconciled_before_any_further_retry(tmp_path):
    class ApplyThenRaise:
        def __init__(self):
            self.effects = []
            self.invocation_count = 0

        def lookup(self, command_id: str) -> DownstreamObservation:
            matches = [payload for key, payload in self.effects if key == command_id]
            return DownstreamObservation(
                ReconciliationStatus.APPLIED if matches else ReconciliationStatus.ABSENT,
                tuple(matches),
                authoritative=True,
            )

        def apply(self, command_id: str, payload: bytes) -> None:
            self.invocation_count += 1
            self.effects.append((command_id, payload))
            raise RuntimeError("transport failed after downstream effect")

    sink = ApplyThenRaise()
    local = LocalOperationStore(tmp_path / "operations.sqlite")
    command_id = "apply-then-raise-010"
    local.record(command_id, "IN_PROGRESS")

    first = recover_before_retry(command_id, b"RELAY:ON", sink, local)
    assert first == "RETRY_OUTCOME_UNKNOWN"
    assert local.outcome(command_id) == "UNKNOWN"
    assert sink.effect_count if hasattr(sink, "effect_count") else len(sink.effects) == 1
    assert sink.invocation_count == 1

    second = recover_before_retry(command_id, b"RELAY:ON", sink, local)
    assert second == "RECONCILED_ALREADY_APPLIED"
    assert local.outcome(command_id) == "SUCCEEDED"
    assert len(sink.effects) == 1
    assert sink.invocation_count == 1
    local.close()
