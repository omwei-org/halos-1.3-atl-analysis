"""Crash/reconciliation tests with independent downstream effect accounting.

The local journal uses SQLite to exercise persistence across store reopen.
The downstream sink remains a deterministic software model, not a real actuator.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


class SimulatedProcessCrash(BaseException):
    """Crash boundary deliberately bypassing ordinary exception handling."""


@dataclass
class DownstreamEffectSink:
    """Independent in-memory observer/actuator model."""

    effects: list[tuple[str, bytes]] = field(default_factory=list)
    invocation_count: int = 0

    def apply(self, command_id: str, payload: bytes) -> None:
        self.invocation_count += 1
        self.effects.append((command_id, payload))

    def find(self, command_id: str) -> list[tuple[str, bytes]]:
        return [effect for effect in self.effects if effect[0] == command_id]

    @property
    def effect_count(self) -> int:
        return len(self.effects)


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


def execute_with_crash_window(
    command_id: str,
    payload: bytes,
    sink: DownstreamEffectSink,
    local: LocalOperationStore,
) -> None:
    """Apply downstream effect, then crash before recording a terminal outcome."""
    local.record(command_id, "IN_PROGRESS")
    sink.apply(command_id, payload)
    raise SimulatedProcessCrash("crash after downstream effect, before outcome record")


def recover_before_retry(
    command_id: str,
    payload: bytes,
    sink: DownstreamEffectSink,
    local: LocalOperationStore,
) -> str:
    """Mark interrupted work UNKNOWN, reconcile downstream, and only then retry."""
    local.mark_interrupted_unknown()

    observed = sink.find(command_id)
    if observed:
        if any(effect_payload != payload for _, effect_payload in observed):
            raise AssertionError("command_id collision: downstream payload mismatch")
        local.record(command_id, "SUCCEEDED")
        return "RECONCILED_ALREADY_APPLIED"

    # This empty result is authoritative only within this in-memory sink model.
    # A real deployment needs a downstream lookup with equivalent guarantees.
    local.record(command_id, "RETRY_AUTHORIZED")
    sink.apply(command_id, payload)
    local.record(command_id, "SUCCEEDED")
    return "RETRIED_AFTER_CONFIRMED_ABSENCE"


def test_crash_after_effect_recovers_persisted_outcome_as_unknown(tmp_path):
    sink = DownstreamEffectSink()
    journal_path = tmp_path / "operations.sqlite"
    local = LocalOperationStore(journal_path)
    command_id = "crash-window-001"

    try:
        execute_with_crash_window(command_id, b"RELAY:ON", sink, local)
    except SimulatedProcessCrash:
        pass
    else:
        raise AssertionError("crash injection did not occur")

    # Crash occurred after the sink effect and before terminal local recording.
    assert local.outcome(command_id) == "IN_PROGRESS"
    assert sink.effect_count == 1
    assert sink.find(command_id) == [(command_id, b"RELAY:ON")]

    # Close and reopen the actual SQLite file to model process restart.
    local.close()
    restarted_local = LocalOperationStore(journal_path)
    assert restarted_local.outcome(command_id) == "IN_PROGRESS"

    # Recovery changes the persisted non-terminal state to UNKNOWN.
    restarted_local.mark_interrupted_unknown()
    assert restarted_local.outcome(command_id) == "UNKNOWN"
    restarted_local.close()


def test_recovery_reconciles_before_retry_and_prevents_duplicate_effect(tmp_path):
    sink = DownstreamEffectSink()
    journal_path = tmp_path / "operations.sqlite"
    local = LocalOperationStore(journal_path)
    command_id = "crash-window-002"

    try:
        execute_with_crash_window(command_id, b"RELAY:ON", sink, local)
    except SimulatedProcessCrash:
        pass

    assert sink.effect_count == 1
    local.close()

    # Reopen the journal as a restarted process, then reconcile before retry.
    restarted_local = LocalOperationStore(journal_path)
    assert restarted_local.outcome(command_id) == "IN_PROGRESS"
    result = recover_before_retry(
        command_id, b"RELAY:ON", sink, restarted_local
    )

    assert result == "RECONCILED_ALREADY_APPLIED"
    assert restarted_local.outcome(command_id) == "SUCCEEDED"
    assert sink.effect_count == 1
    assert sink.invocation_count == 1
    assert len(sink.find(command_id)) == 1
    restarted_local.close()


def test_recovery_retries_only_after_downstream_confirms_no_effect(tmp_path):
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


def test_duplicate_downstream_effect_is_visible_to_independent_counter():
    sink = DownstreamEffectSink()
    command_id = "duplicate-004"

    sink.apply(command_id, b"RELAY:ON")
    sink.apply(command_id, b"RELAY:ON")

    # The sink intentionally has no idempotency behavior: it exposes duplicates.
    assert sink.invocation_count == 2
    assert sink.effect_count == 2
    assert len(sink.find(command_id)) == 2
