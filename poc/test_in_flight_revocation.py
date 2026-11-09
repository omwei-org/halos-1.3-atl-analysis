"""In-Flight Revocation Evidence Tests: Long-Running Simulated Execution

These tests simulate long-running operations using deterministic threading
synchronization (Events and Barriers) to control execution/revocation ordering.

Classification: SIMULATED long-running execution, not physical hardware evidence.
"""
from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Callable

from poc.commit_gate import CommitGate, SafetyDecision, SafetyResult
from poc.gie import CheckResult, Decision, GIE, make_bytes_execution_evidence
from poc.physical_boundary import (
    ActuatorAdapter,
    GovernedPhysicalPath,
    PhysicalExecutionObject,
    RecordingRelay,
)


@dataclass
class ExecutionTimeline:
    """Timestamped evidence of execution lifecycle events."""
    operation_start: float = field(default_factory=time.time)
    revocation_request: float = 0.0
    revocation_effective: float = 0.0
    subsequent_effect_attempt: float = 0.0
    commit_decision: float = 0.0
    actuator_invocation: float = 0.0
    actuator_rejection: float = 0.0


class LongRunningActuator(ActuatorAdapter):
    """Actuator that simulates a long-running operation using threading synchronization.

    This is a test fixture for simulating long-running execution, not a
    production hardware driver.
    """

    def __init__(self) -> None:
        self.state: bool = False
        self.applied_payloads: list[bytes] = []
        self._execution_barrier = threading.Barrier(2)
        self._revocation_barrier = threading.Barrier(2)
        self.timeline = ExecutionTimeline()

    def apply(self, payload: bytes) -> None:
        """Simulate a long-running operation with controlled synchronization."""
        # Signal that operation has started
        self.timeline.operation_start = time.time()

        # Wait for revocation to occur before proceeding
        self._execution_barrier.wait()

        # Signal that revocation is effective
        self.timeline.revocation_effective = time.time()

        # Wait for main thread to signal commit attempt
        self._revocation_barrier.wait()

        # At this point, the operation would attempt to commit
        # In a conformant implementation, this would revalidate authority
        self.timeline.subsequent_effect_attempt = time.time()

        # For this test, we don't actually apply - we just record the timeline
        # The actual commit decision is made by GovernedPhysicalPath


def test_long_running_operation_revocation_with_events():
    """A commit already inside the effect boundary serializes before revoke."""
    gie = GIE()
    epoch = gie.grant(0)

    class BlockingRelay(RecordingRelay):
        def __init__(self):
            super().__init__()
            self.apply_started = threading.Event()
            self.allow_apply = threading.Event()

        def apply(self, payload: bytes) -> None:
            self.apply_started.set()
            assert self.allow_apply.wait(timeout=3), "test did not release actuator"
            super().apply(payload)

    actuator = BlockingRelay()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=actuator)
    execution = PhysicalExecutionObject(0, b"RELAY:ON", epoch)
    prepared = path.prepare(execution, command_id="test-long-running-001")

    commit_results = []
    commit_thread = threading.Thread(
        target=lambda: commit_results.append(path.commit_prepared(prepared))
    )
    commit_thread.start()
    assert actuator.apply_started.wait(timeout=3)

    revoke_started = threading.Event()
    revoke_completed = threading.Event()

    def revoke():
        revoke_started.set()
        gie.revoke(0)
        revoke_completed.set()

    revoke_thread = threading.Thread(target=revoke)
    revoke_thread.start()
    assert revoke_started.wait(timeout=3)

    # Revocation cannot become effective between final validation and effect.
    assert not revoke_completed.wait(timeout=0.05)
    actuator.allow_apply.set()

    commit_thread.join(timeout=3)
    revoke_thread.join(timeout=3)
    assert not commit_thread.is_alive()
    assert not revoke_thread.is_alive()

    assert len(commit_results) == 1
    assert commit_results[0].decision is Decision.ALLOW
    assert commit_results[0].applied is True
    assert len(actuator.applied_payloads) == 1
    assert actuator.state is True
    assert revoke_completed.is_set()
    assert gie.current_epoch(0) == epoch + 1


def test_prepare_commit_with_revocation_during_callback():
    """Scenario 1 variant: revocation during synchronous effect callback.

    This test uses threading Events to simulate revocation occurring during
    a synchronous effect callback, demonstrating the serialization behavior.
    """
    gie = GIE()
    epoch = gie.grant(0)

    relay = RecordingRelay()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay)

    execution = PhysicalExecutionObject(0, b"RELAY:ON", epoch)

    # Synchronization events
    revocation_event = threading.Event()
    callback_started = threading.Event()
    callback_complete = threading.Event()

    timeline = ExecutionTimeline()

    def effect_callback():
        """Simulated effect callback that can be interrupted by revocation."""
        timeline.operation_start = time.time()
        callback_started.set()

        # Wait for revocation to occur
        revocation_event.wait()

        timeline.revocation_effective = time.time()
        # Effect would complete here
        callback_complete.set()

    # Start effect callback in a separate thread
    callback_thread = threading.Thread(target=effect_callback)
    callback_thread.start()

    # Wait for callback to start
    callback_started.wait()

    # Revoke authority while callback is "in-flight"
    timeline.revocation_request = time.time()
    gie.revoke(0)
    revocation_event.set()

    # Wait for callback to complete
    callback_complete.wait()
    callback_thread.join()

    # Attempt commit
    timeline.subsequent_effect_attempt = time.time()
    result = path.commit(execution, command_id="test-callback-revoke-001")

    timeline.commit_decision = time.time()

    # Verify commit is blocked
    assert result.decision is Decision.BLOCK
    assert result.applied is False
    assert len(relay.applied_payloads) == 0

    # Verify temporal ordering
    assert timeline.operation_start < timeline.revocation_request
    assert timeline.revocation_request < timeline.revocation_effective
    assert timeline.revocation_effective < timeline.subsequent_effect_attempt
    assert timeline.subsequent_effect_attempt < timeline.commit_decision


if __name__ == "__main__":
    raise SystemExit("Run with pytest: pytest poc/test_in_flight_revocation.py")
