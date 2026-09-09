from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Optional

import torch


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
    """Non-authoritative evidence attached to one concrete generated action.

    The evidence identifies the action and records the authority epoch observed by
    the execution pipeline. It does not contain or assert authority state.
    """

    env_id: int
    action_epoch: int
    action_digest: str


@dataclass(frozen=True)
class CheckResult:
    """Deterministic result of one execution-authority check."""

    decision: Decision
    reason: str
    action_epoch: int
    authority_epoch: int


def action_digest(action: torch.Tensor) -> str:
    """Return a deterministic digest for the concrete tensor execution object."""
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
    """Create non-authoritative evidence for one concrete generated action."""
    return ExecutionEvidence(
        env_id=env_id,
        action_epoch=action_epoch,
        action_digest=action_digest(action),
    )


class GIE:
    """Minimal policy-, scheduler-, and embodiment-neutral authority gate."""

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
        """Check evidence against GIE-owned authority and the concrete action.

        ``evidence`` is treated only as caller-supplied evidence. Authority is
        resolved exclusively from GIE-internal state via ``self._ctx``.
        """
        if evidence.env_id < 0:
            return CheckResult(
                Decision.BLOCK,
                "invalid_env_id",
                evidence.action_epoch,
                -1,
            )

        if action_digest(action) != evidence.action_digest:
            return CheckResult(
                Decision.BLOCK,
                "action_digest_mismatch",
                evidence.action_epoch,
                self.current_epoch(evidence.env_id),
            )

        return self.check(
            env_id=evidence.env_id,
            action=action,
            action_epoch=evidence.action_epoch,
        )

    def check(
        self,
        env_id: int,
        action: torch.Tensor,
        action_epoch: int,
        authority_context: Optional[AuthorityContext] = None,
    ) -> CheckResult:
        """Check whether one generated action currently has execution authority."""
        # ``action`` is intentionally part of the contract even though v0.1 does
        # not inspect its value. It permits future binding/evidence checks.
        _ = action

        ctx = authority_context or self._ctx.get(env_id)
        if ctx is None:
            return CheckResult(
                Decision.BLOCK,
                "no_authority_context",
                action_epoch,
                -1,
            )

        if ctx.revoked:
            return CheckResult(
                Decision.BLOCK,
                "revoked",
                action_epoch,
                ctx.epoch,
            )

        if action_epoch != ctx.epoch:
            return CheckResult(
                Decision.BLOCK,
                "epoch_mismatch",
                action_epoch,
                ctx.epoch,
            )

        return CheckResult(
            Decision.ALLOW,
            "authorized",
            action_epoch,
            ctx.epoch,
        )
