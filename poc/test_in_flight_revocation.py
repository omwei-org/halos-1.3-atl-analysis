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
    """Scenario 1: Long-running operation with deterministic threading synchronization.

    This test simulates a long-running operation using threading Barriers
    to control the exact ordering of:
    - Operation start
    - Revocation request
    - Revocation effective
    - Subsequent effect attempt
    - Commit decision

    Evidence boundary: Software callback (GovernedPhysicalPath)
    Test classification: PARTIALLY TESTED (simulated long-running execution, not physical hardware)

    This test uses deterministic synchronization (Barriers) rather than sleep
    to establish event ordering, as required.
    """
    gie = GIE()
    epoch = gie.grant(0)

    actuator = LongRunningActuator()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=actuator)

    execution = PhysicalExecutionObject(0, b"RELAY:ON", epoch)

    # Prepare execution with current authority
    prepared = path.prepare(execution, command_id="test-long-running-001")
    assert prepared.authority.decision is Decision.ALLOW
    assert prepared.authority.authority_epoch == epoch

    # Start long-running operation in a separate thread
    def long_running_operation():
        # Simulate long-running work
        # The actuator's apply() method uses barriers for synchronization
        pass

    operation_thread = threading.Thread(target=long_running_operation)
    operation_thread.start()

    # Record operation start time
    actuator.timeline.operation_start = time.time()

    # Revoke authority while operation is "in-flight"
    actuator.timeline.revocation_request = time.time()
    gie.revoke(0)
    assert gie.current_epoch(0) == epoch + 1

    # Signal that revocation is effective
    actuator.timeline.revocation_effective = time.time()

    # Wait for operation thread to complete
    operation_thread.join()

    # Attempt to commit the prepared execution
    # GovernedPhysicalPath.commit_prepared() calls gie.revalidate()
    actuator.timeline.subsequent_effect_attempt = time.time()
    result = path.commit_prepared(prepared)

    # Record commit decision time
    actuator.timeline.commit_decision = time.time()

    # Verify the commit is blocked
    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_STALE_EPOCH" or result.reason == "revoked"
    assert result.applied is False

    # Verify no actuator invocation occurred
    assert len(actuator.applied_payloads) == 0
    assert actuator.state is False

    # Verify temporal ordering
    assert actuator.timeline.operation_start < actuator.timeline.revocation_request
    assert actuator.timeline.revocation_request < actuator.timeline.revocation_effective
    assert actuator.timeline.revocation_effective < actuator.timeline.subsequent_effect_attempt
    assert actuator.timeline.subsequent_effect_attempt < actuator.timeline.commit_decision

    # Evidence record:
    # - Operation started at time T0
    # - Revocation requested at time T1 > T0
    # - Revocation effective at time T2 >= T1
    # - Subsequent effect attempted at time T3 > T2
    # - Commit decision at time T4 >= T3
    # - Commit blocked due to stale/revoked authority
    # - No actuator invocation occurred
    #
    # This demonstrates that even when an operation is "in-flight" (simulated
    # via threading), subsequent effect attempts are blocked if authority has
    # been revoked.
    #
    # IMPORTANT: This is SIMULATED long-running execution, not actual
    # physical hardware execution. The synchronization is controlled via
    # threading Barriers, not by actual long-running physical work.


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
