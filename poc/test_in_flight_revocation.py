"""In-flight revocation test at the actual simulated effect boundary.

The test establishes the linearization rule: once commit enters the shared
GIE critical section and begins actuator application, revocation waits until
that effect attempt completes. It does not claim physical hardware evidence.
"""
from __future__ import annotations

import threading

from poc.gie import Decision, GIE
from poc.physical_boundary import (
    GovernedPhysicalPath,
    PhysicalExecutionObject,
    RecordingRelay,
)


def test_revoke_serializes_behind_commit_already_inside_effect_boundary():
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

    # The effect has entered the critical section; revoke cannot linearize yet.
    assert not revoke_completed.wait(timeout=0.05)
    actuator.allow_apply.set()

    commit_thread.join(timeout=3)
    revoke_thread.join(timeout=3)
    assert not commit_thread.is_alive()
    assert not revoke_thread.is_alive()

    assert len(commit_results) == 1
    assert commit_results[0].decision is Decision.ALLOW
    assert commit_results[0].applied is True
    assert actuator.applied_payloads == [b"RELAY:ON"]
    assert actuator.state is True
    assert revoke_completed.is_set()
    assert gie.current_epoch(0) == epoch + 1
