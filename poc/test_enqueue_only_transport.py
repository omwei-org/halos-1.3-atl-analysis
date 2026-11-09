"""In-Flight Revocation Evidence Tests: Enqueue-Only Transport Scenarios

These tests demonstrate the critical distinction between:
- Acceptance of an operation by a transport/scheduler
- Actual physical effect commit

Scenario 2B tests the architectural failure mode where authorization is checked
only before enqueueing, not at the actual effect-commit boundary.
"""
from __future__ import annotations

import time
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
class QueuedOperation:
    """A deferred operation held in an internal queue."""
    execution: PhysicalExecutionObject
    authority: CheckResult
    safety: SafetyResult
    command_id: str
    queued_at: float = field(default_factory=time.time)


class EnqueueOnlyTransport(ActuatorAdapter):
    """Deliberately non-conformant transport that accepts operations into a queue
    without executing them synchronously.

    This transport demonstrates the architectural failure mode documented in
    Comos effect_boundary.py: "A transport that only enqueues work is NOT
    conformant: the authority lock would be released before the queued command
    takes effect."

    This is a NEGATIVE CONTROL - it demonstrates what happens when authorization
    is checked only before enqueueing, not at the actual effect boundary.
    """

    def __init__(self) -> None:
        self.queue: list[QueuedOperation] = []
        self.executed_operations: list[QueuedOperation] = []
        self._released = False

    def apply(self, payload: bytes) -> None:
        """This implementation ignores the standard apply() contract.

        Operations are queued instead of executed synchronously.
        """
        # For the negative control test, we'll use a different interface
        pass

    def enqueue(
        self,
        execution: PhysicalExecutionObject,
        authority: CheckResult,
        safety: SafetyResult,
        command_id: str,
    ) -> None:
        """Accept an operation into the internal queue without executing it."""
        self.queue.append(QueuedOperation(
            execution=execution,
            authority=authority,
            safety=safety,
            command_id=command_id,
        ))

    def release_queue(self) -> None:
        """Execute all queued operations synchronously.

        This method simulates the delayed execution that would occur in a
        real enqueue-only transport. In a conformant implementation, each
        operation would revalidate authority at this point. This non-conformant
        implementation does NOT revalidate, demonstrating the failure mode.
        """
        self._released = True
        for op in self.queue:
            # Simulate execution without revalidating authority
            # This is the failure mode: stale authority can execute
            self.executed_operations.append(op)
        self.queue.clear()


def test_non_conformant_enqueue_only_transport_failure_mode():
    """Scenario 2B-A: Non-conformant enqueue-only transport negative control.

    This test demonstrates the architectural failure mode:
    1. Transport accepts operation into queue (authority checked at enqueue time)
    2. Authority is revoked
    3. Queue is released
    4. Stale operation executes (failure mode - no revalidation at effect boundary)

    Evidence boundary: Transport layer (EnqueueOnlyTransport)
    Test classification: PARTIALLY TESTED (demonstrates failure mode of non-conformant transport)
    """
    gie = GIE()
    epoch = gie.grant(0)

    transport = EnqueueOnlyTransport()
    gate = CommitGate()

    # Prepare execution with current authority
    execution = PhysicalExecutionObject(0, b"RELAY:ON", epoch)
    evidence = make_bytes_execution_evidence(0, execution.payload, epoch)
    authority = gie.check_bytes_evidence(evidence, execution.payload)
    safety = SafetyResult(SafetyDecision.ALLOW, "halos_safe", evidence.action_digest)
    command_id = "test-001"

    # Verify initial authority is ALLOW
    assert authority.decision is Decision.ALLOW
    assert authority.authority_epoch == epoch

    # Enqueue operation (simulating transport acceptance)
    enqueue_time = time.time()
    transport.enqueue(execution, authority, safety, command_id)
    assert len(transport.queue) == 1
    assert transport.queue[0].authority.decision is Decision.ALLOW

    # Revoke authority while operation is queued
    revoke_time = time.time()
    gie.revoke(0)
    assert gie.current_epoch(0) == epoch + 1

    # Release queue (simulate delayed execution)
    release_time = time.time()
    transport.release_queue()

    # In this non-conformant implementation, the stale operation executes
    # This demonstrates the failure mode
    assert len(transport.executed_operations) == 1
    executed_op = transport.executed_operations[0]
    assert executed_op.authority.decision is Decision.ALLOW
    assert executed_op.authority.authority_epoch == epoch  # STALE epoch

    # Verify temporal ordering
    assert enqueue_time < revoke_time < release_time

    # This test demonstrates the failure mode:
    # - Operation was accepted at time T0 with authority epoch N
    # - Authority was revoked at time T1 > T0 (epoch N+1)
    # - Operation executed at time T2 > T1 using stale authority epoch N
    # - No revalidation occurred at the effect boundary
    #
    # This is the documented failure mode of enqueue-only transports that
    # do not revalidate authority at the actual effect-commit boundary.


def test_guarded_enqueue_with_halos_authority_revalidation():
    """Scenario 2B-B: Guarded enqueue with real HALOS authority revalidation.

    This test uses the real HALOS GovernedPhysicalPath to demonstrate
    that authorization IS revalidated at the commit boundary, preventing
    stale queued operations from executing.

    If the current architecture cannot reject the queued operation at
    execution time, this test will fail, serving as evidence of the gap.

    Evidence boundary: GovernedPhysicalPath commit boundary
    Test classification: TESTED (if passes) or PARTIALLY TESTED (if reveals gap)
    """
    gie = GIE()
    epoch = gie.grant(0)

    # Use RecordingRelay as the actuator (test double, not hardware)
    relay = RecordingRelay()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay)

    # Prepare execution with current authority
    execution = PhysicalExecutionObject(0, b"RELAY:ON", epoch)

    # Stage 1: Prepare execution (authority checked at prepare time)
    prepare_time = time.time()
    prepared = path.prepare(execution, command_id="test-002")

    # Verify preparation succeeded
    assert prepared.authority.decision is Decision.ALLOW
    assert prepared.authority.authority_epoch == epoch
    assert prepared.safety.decision is SafetyDecision.ALLOW

    # Stage 2: Revoke authority while operation is prepared but not committed
    revoke_time = time.time()
    gie.revoke(0)
    assert gie.current_epoch(0) == epoch + 1

    # Stage 3: Attempt to commit the prepared execution
    # GovernedPhysicalPath.commit_prepared() calls gie.revalidate() before
    # the CommitGate, so this should block the stale operation
    commit_time = time.time()
    result = path.commit_prepared(prepared)

    # Verify the commit is blocked
    assert result.decision is Decision.BLOCK
    assert result.reason == "authority_STALE_EPOCH" or result.reason == "revoked"
    assert result.applied is False

    # Verify no actuator invocation occurred
    assert len(relay.applied_payloads) == 0
    assert relay.state is False

    # Verify temporal ordering
    assert prepare_time < revoke_time < commit_time

    # Evidence record:
    # - Execution prepared at time T0 with authority epoch N
    # - Authority revoked at time T1 > T0 (epoch N+1)
    # - Commit attempted at time T2 > T1
    # - GovernedPhysicalPath.revalidate() detected stale epoch
    # - CommitGate blocked the operation
    # - No actuator invocation occurred
    #
    # This demonstrates that the HALOS architecture DOES revalidate
    # authority at the commit boundary, preventing stale queued operations
    # from executing.


def test_guarded_enqueue_positive_control():
    """Positive control: authorized execution should succeed through guarded enqueue.

    This test verifies that the guarded enqueue path works correctly when
    authority is NOT revoked.
    """
    gie = GIE()
    epoch = gie.grant(0)

    relay = RecordingRelay()
    path = GovernedPhysicalPath(gie, env_id=0, actuator=relay)

    execution = PhysicalExecutionObject(0, b"RELAY:ON", epoch)

    # Prepare and commit without revocation
    prepared = path.prepare(execution, command_id="test-003")
    result = path.commit_prepared(prepared)

    # Verify success
    assert result.decision is Decision.ALLOW
    assert result.applied is True
    assert len(relay.applied_payloads) == 1
    assert relay.state is True


if __name__ == "__main__":
    raise SystemExit("Run with pytest: pytest poc/test_enqueue_only_transport.py")
