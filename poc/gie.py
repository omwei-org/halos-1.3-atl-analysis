from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Optional

import torch

from poc.execution_identity import ExecutionIdentity, digest_bytes


class Decision(Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class AuthorityContext:
    """Current execution-authority state for one environment."""

    epoch: int
    revoked: bool = False


@dataclass(frozen=True)
class ExecutionEvidence:
    """Non-authoritative evidence for one concrete execution object."""

    env_id: int
    identity: ExecutionIdentity

    @property
    def action_epoch(self) -> int:
        return self.identity.execution_epoch

    @property
    def action_digest(self) -> str:
        return self.identity.digest


@dataclass(frozen=True)
class CheckResult:
    """Deterministic authority result bound to one concrete execution identity."""

    decision: Decision
    reason: str
    action_epoch: int
    authority_epoch: int
    action_digest: str


def action_digest(action: torch.Tensor) -> str:
    """Compatibility digest for the existing tensor execution object."""
    tensor = action.detach().cpu().contiguous()
    payload = (
        str(tensor.dtype).encode("utf-8")
        + b"|"
        + repr(tuple(tensor.shape)).encode("utf-8")
        + b"|"
        + tensor.numpy().tobytes()
    )
    return sha256(payload).hexdigest()


def make_execution_evidence(
    env_id: int,
    action: torch.Tensor,
    action_epoch: int,
) -> ExecutionEvidence:
    """Create non-authoritative evidence for a tensor execution object."""
    identity = ExecutionIdentity(
        digest=action_digest(action),
        execution_epoch=action_epoch,
    )
    return ExecutionEvidence(env_id=env_id, identity=identity)


def make_bytes_execution_evidence(
    env_id: int,
    payload: bytes,
    execution_epoch: int,
) -> ExecutionEvidence:
    """Create non-authoritative evidence for an exact byte execution object."""
    identity = ExecutionIdentity(
        digest=digest_bytes(payload),
        execution_epoch=execution_epoch,
    )
    return ExecutionEvidence(env_id=env_id, identity=identity)


class GIE:
    """Policy-, scheduler-, and embodiment-neutral authority gate."""

    def __init__(self, default_epoch: int = 0) -> None:
        self._ctx: dict[int, AuthorityContext] = {}
        self._default_epoch = default_epoch

    def grant(self, env_id: int, epoch: Optional[int] = None) -> int:
        """Issue or renew authority and return its epoch."""
        if epoch is None:
            current = self._ctx.get(env_id)
            base = current.epoch if current is not None else self._default_epoch
            epoch = base + 1
        self._ctx[env_id] = AuthorityContext(epoch=epoch, revoked=False)
        return epoch

    def revoke(self, env_id: int) -> None:
        """Revoke current authority without changing its epoch."""
        current = self._ctx.get(env_id)
        epoch = current.epoch if current is not None else self._default_epoch
        self._ctx[env_id] = AuthorityContext(epoch=epoch, revoked=True)

    def current_epoch(self, env_id: int) -> int:
        current = self._ctx.get(env_id)
        return current.epoch if current is not None else self._default_epoch

    def check_evidence(
        self,
        evidence: ExecutionEvidence,
        action: torch.Tensor,
    ) -> CheckResult:
        """Check evidence against GIE-owned authority and the concrete action."""
        if evidence.env_id < 0:
            return CheckResult(
                Decision.BLOCK,
                "invalid_env_id",
                evidence.action_epoch,
                -1,
                evidence.action_digest,
            )

        if action_digest(action) != evidence.action_digest:
            return CheckResult(
                Decision.BLOCK,
                "action_digest_mismatch",
                evidence.action_epoch,
                self.current_epoch(evidence.env_id),
                action_digest(action),
            )

        return self.check(
            env_id=evidence.env_id,
            action=action,
            action_epoch=evidence.action_epoch,
            execution_digest=evidence.action_digest,
        )

    def check_bytes_evidence(
        self,
        evidence: ExecutionEvidence,
        payload: bytes,
    ) -> CheckResult:
        """Check exact byte evidence against GIE-owned authority."""
        if evidence.env_id < 0:
            return CheckResult(
                Decision.BLOCK,
                "invalid_env_id",
                evidence.action_epoch,
                -1,
                evidence.action_digest,
            )

        actual_digest = digest_bytes(payload)
        if actual_digest != evidence.action_digest:
            return CheckResult(
                Decision.BLOCK,
                "action_digest_mismatch",
                evidence.action_epoch,
                self.current_epoch(evidence.env_id),
                actual_digest,
            )

        return self.check(
            env_id=evidence.env_id,
            action=None,
            action_epoch=evidence.action_epoch,
            execution_digest=actual_digest,
        )

    def check(
        self,
        env_id: int,
        action: object,
        action_epoch: int,
        authority_context: Optional[AuthorityContext] = None,
        execution_digest: Optional[str] = None,
    ) -> CheckResult:
        """Check current authority; caller-supplied context is test/offline only."""
        digest = execution_digest or ""
        _ = action

        ctx = authority_context or self._ctx.get(env_id)
        if ctx is None:
            return CheckResult(
                Decision.BLOCK,
                "no_authority_context",
                action_epoch,
                -1,
                digest,
            )

        if ctx.revoked:
            return CheckResult(Decision.BLOCK, "revoked", action_epoch, ctx.epoch, digest)

        if action_epoch != ctx.epoch:
            return CheckResult(Decision.BLOCK, "epoch_mismatch", action_epoch, ctx.epoch, digest)

        return CheckResult(Decision.ALLOW, "authorized", action_epoch, ctx.epoch, digest)

    def revalidate(
        self,
        env_id: int,
        authority: CheckResult,
        action: object,
        execution_digest: Optional[str] = None,
    ) -> CheckResult:
        """Re-read GIE authority immediately before the execution commit."""
        digest = execution_digest or authority.action_digest
        if digest != authority.action_digest:
            return CheckResult(
                Decision.BLOCK,
                "action_digest_mismatch",
                authority.action_epoch,
                self.current_epoch(env_id),
                digest,
            )

        fresh = self.check(
            env_id=env_id,
            action=action,
            action_epoch=authority.action_epoch,
            execution_digest=digest,
        )
        if fresh.decision is Decision.BLOCK:
            return fresh

        if fresh.authority_epoch != authority.authority_epoch:
            return CheckResult(
                Decision.BLOCK,
                "authority_epoch_changed",
                authority.action_epoch,
                fresh.authority_epoch,
                digest,
            )

        return fresh
