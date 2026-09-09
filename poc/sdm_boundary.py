from __future__ import annotations

from dataclasses import dataclass

from poc.atl_boundary import ATLCommitBoundary, ATLCommitResult, ATLExecutionObject
from poc.commit_gate import SafetyResult
from poc.gie import CheckResult


@dataclass(frozen=True)
class SDMCommand:
    """Exact ATL command emitted by the Halos SDM boundary."""

    env_id: int
    packet: bytes
    governance_epoch: int


class SDMCommitAdapter:
    """Bind an SDM-produced exact packet to the final Commit Gate boundary.

    The adapter treats the SDM packet as opaque bytes. It does not decode,
    rewrite, regenerate CRCs, alter sequence counters, or otherwise interpret
    ATL command fields. On ALLOW the exact packet supplied by SDM is returned.
    On BLOCK no transmit payload is produced.
    """

    def __init__(self, boundary: ATLCommitBoundary) -> None:
        self._boundary = boundary

    def commit(
        self,
        command: SDMCommand,
        authority: CheckResult,
        safety: SafetyResult,
    ) -> ATLCommitResult:
        execution = ATLExecutionObject(
            env_id=command.env_id,
            packet=command.packet,
            governance_epoch=command.governance_epoch,
        )
        return self._boundary.commit(execution, authority, safety)

    def transmit_payload(
        self,
        command: SDMCommand,
        result: ATLCommitResult,
    ) -> bytes | None:
        execution = ATLExecutionObject(
            env_id=command.env_id,
            packet=command.packet,
            governance_epoch=command.governance_epoch,
        )
        return self._boundary.transmit_payload(execution, result)
