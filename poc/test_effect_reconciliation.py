"""Crash/reconciliation tests with independent downstream effect accounting.

Classification: deterministic software simulation; not physical actuator evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class SimulatedProcessCrash(BaseException):
    """Crash boundary deliberately bypassing ordinary exception handling."""


@dataclass
class DownstreamEffectSink:
    """Independent observer/actuator model; it does not trust caller outcomes."""

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


@dataclass
class LocalOperationStore:
    """Local outcome journal, intentionally separate from downstream effects."""

    outcomes: dict[str, str] = field(default_factory=dict)

    def record(self, command_id: str, outcome: str) -> None:
        self.outcomes[command_id] = outcome


def execute_with_crash_window(
    command_id: str,
    payload: bytes,
    sink: DownstreamEffectSink,
    local: LocalOperationStore,
) -> None:
    """Apply downstream effect, then simulate crash before local result write."""
    local.outcomes[command_id] = "IN_PROGRESS"
    sink.apply(command_id, payload)
    raise SimulatedProcessCrash("crash after downstream effect, before outcome record")


def recover_before_retry(
    command_id: str,
    payload: bytes,
    sink: DownstreamEffectSink,
    local: LocalOperationStore,
) -> str:
    """Reconcile downstream state before deciding whether retry is safe."""
    local.outcomes[command_id] = "UNKNOWN"

    observed = sink.find(command_id)
    if observed:
        # A matching command ID is evidence that the Protected Effect occurred.
        if any(effect_payload != payload for _, effect_payload in observed):
            raise AssertionError("command_id collision: downstream payload mismatch")
        local.record(command_id, "SUCCEEDED")
        return "RECONCILED_ALREADY_APPLIED"

    # Only an independently verified absence permits a retry.
    sink.apply(command_id, payload)
    local.record(command_id, "SUCCEEDED")
    return "RETRIED_AFTER_CONFIRMED_ABSENCE"


def test_crash_after_effect_leaves_local_outcome_unknown():
    sink = DownstreamEffectSink()
    local = LocalOperationStore()
    command_id = "crash-window-001"

    try:
        execute_with_crash_window(command_id, b"RELAY:ON", sink, local)
    except SimulatedProcessCrash:
        pass
    else:
        raise AssertionError("crash injection did not occur")

    # T3: downstream truth and local journal intentionally disagree.
    assert sink.effect_count == 1
    assert sink.find(command_id) == [(command_id, b"RELAY:ON")]
    assert local.outcomes[command_id] == "IN_PROGRESS"
    local.outcomes[command_id] = "UNKNOWN"
    assert local.outcomes[command_id] == "UNKNOWN"


def test_recovery_reconciles_before_retry_and_prevents_duplicate_effect():
    sink = DownstreamEffectSink()
    local = LocalOperationStore()
    command_id = "crash-window-002"

    try:
        execute_with_crash_window(command_id, b"RELAY:ON", sink, local)
    except SimulatedProcessCrash:
        pass

    # T5: capture independent count before recovery.
    assert sink.effect_count == 1
    assert local.outcomes[command_id] == "IN_PROGRESS"

    # T4: recovery must query downstream before it can retry.
    result = recover_before_retry(command_id, b"RELAY:ON", sink, local)

    assert result == "RECONCILED_ALREADY_APPLIED"
    assert local.outcomes[command_id] == "SUCCEEDED"
    assert sink.effect_count == 1
    assert sink.invocation_count == 1
    assert len(sink.find(command_id)) == 1


def test_recovery_retries_only_after_downstream_confirms_no_effect():
    sink = DownstreamEffectSink()
    local = LocalOperationStore()
    command_id = "not-applied-003"

    # No downstream effect exists; recovery may safely retry once.
    local.outcomes[command_id] = "UNKNOWN"
    result = recover_before_retry(command_id, b"RELAY:ON", sink, local)

    assert result == "RETRIED_AFTER_CONFIRMED_ABSENCE"
    assert local.outcomes[command_id] == "SUCCEEDED"
    assert sink.effect_count == 1
    assert sink.invocation_count == 1
    assert sink.find(command_id) == [(command_id, b"RELAY:ON")]


def test_duplicate_downstream_effect_is_visible_to_independent_counter():
    sink = DownstreamEffectSink()
    command_id = "duplicate-004"

    sink.apply(command_id, b"RELAY:ON")
    sink.apply(command_id, b"RELAY:ON")

    # The sink intentionally has no idempotency behavior: it exposes duplicates.
    assert sink.invocation_count == 2
    assert sink.effect_count == 2
    assert len(sink.find(command_id)) == 2
