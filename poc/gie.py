from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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
class CheckResult:
    """Deterministic result of one execution-authority check."""

    decision: Decision
    reason: str
    action_epoch: int
    authority_epoch: int


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
