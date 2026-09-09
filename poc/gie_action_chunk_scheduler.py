from __future__ import annotations

from collections.abc import Callable

import torch

from isaaclab_arena.policy.action_scheduling.action_chunk_scheduler import ActionChunkScheduler
from poc.gie import Decision, GIE, ExecutionEvidence, make_execution_evidence


class GIEActionChunkScheduler:
    """Thin execution-authority enforcement layer around a real ActionChunkScheduler.

    The underlying scheduler owns chunk fetch, buffering, indexing, exhaustion, and reset.
    This layer only stamps execution evidence at fetch time and evaluates the selected
    action at commit time. It therefore remains independent of GR00T, the policy
    implementation, and the robot embodiment.

    Security boundary: this adapter carries execution evidence, never AuthorityContext.
    Authority is always resolved inside GIE.
    """

    def __init__(self, scheduler: ActionChunkScheduler, gie: GIE) -> None:
        self.scheduler = scheduler
        self.gie = gie
        self.num_envs = scheduler.num_envs
        self.device = scheduler.device
        self.action_dim = scheduler.action_dim

        # Epoch observed when the currently buffered chunk was fetched, one value per env.
        self.action_epoch = torch.full(
            (self.num_envs,),
            -1,
            dtype=torch.int64,
            device=self.device,
        )

        # Digest of the concrete action selected from the currently buffered chunk.
        # This is evidence, not authority.
        self.action_digest: list[str | None] = [None] * self.num_envs

        # Last action that passed the authority check. Used as the default safe hold.
        self.last_authorized = torch.zeros(
            (self.num_envs, self.action_dim),
            dtype=torch.float32,
            device=self.device,
        )

        # Lightweight PoC observability. Keep counters outside the scheduler so that
        # the upstream scheduler remains untouched.
        self.allowed_actions = 0
        self.blocked_actions = 0
        self.block_reasons: dict[str, int] = {}

    def get_action(
        self,
        fetch_action_tensor_fn: Callable[[], torch.Tensor],
        hold_action: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Fetch/extract through the real scheduler, then enforce authority per action.

        The fetch wrapper is deliberately used only to observe the scheduler's own
        ``env_requires_new_chunk`` decision. The actual chunk mutation and index handling
        remain entirely inside ``ActionChunkScheduler``.
        """
        needs_fetch = self.scheduler.env_requires_new_chunk.clone()

        def stamped_fetch() -> torch.Tensor:
            chunk = fetch_action_tensor_fn()
            if chunk.shape[0] != self.num_envs:
                raise ValueError(
                    f"fetch returned {chunk.shape=}; expected first dimension {self.num_envs}"
                )

            # Authority epoch is captured as evidence at generation/fetch time, not
            # when the action is later consumed from the cache. This is the key H3 property.
            for env_id in needs_fetch.nonzero(as_tuple=False).flatten().tolist():
                self.action_epoch[env_id] = self.gie.current_epoch(env_id)
            return chunk

        # Real scheduler semantics happen here: fetch if needed, select current index,
        # advance index, clear exhausted slots, and mark envs for the next fetch.
        candidate = self.scheduler.get_action(stamped_fetch, hold_action=None)

        if candidate.shape != (self.num_envs, self.action_dim):
            raise ValueError(
                f"scheduler returned {candidate.shape=}; "
                f"expected ({self.num_envs}, {self.action_dim})"
            )

        out = candidate.clone()
        selected_hold = hold_action if hold_action is not None else self.last_authorized
        if selected_hold.shape != (self.num_envs, self.action_dim):
            raise ValueError(
                f"hold action has {selected_hold.shape=}; "
                f"expected ({self.num_envs}, {self.action_dim})"
            )

        for env_id in range(self.num_envs):
            evidence: ExecutionEvidence = make_execution_evidence(
                env_id=env_id,
                action=candidate[env_id],
                action_epoch=int(self.action_epoch[env_id].item()),
            )
            self.action_digest[env_id] = evidence.action_digest

            result = self.gie.check_evidence(
                evidence=evidence,
                action=candidate[env_id],
            )

            if result.decision == Decision.BLOCK:
                self.blocked_actions += 1
                self.block_reasons[result.reason] = self.block_reasons.get(result.reason, 0) + 1
                out[env_id] = selected_hold[env_id]
            else:
                self.allowed_actions += 1
                self.last_authorized[env_id] = candidate[env_id].clone()

        return out

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        """Reset scheduler state and invalidate buffered execution evidence.

        The last authorized action is intentionally retained so a subsequent blocked
        action can still use it as a safe hold. A reset does not itself grant authority.
        """
        self.scheduler.reset(env_ids)

        if env_ids is None:
            env_ids = slice(None)
        self.action_epoch[env_ids] = -1

        if isinstance(env_ids, slice):
            self.action_digest = [None] * self.num_envs
        else:
            for env_id in env_ids.tolist():
                self.action_digest[env_id] = None

    @property
    def current_action_index(self) -> torch.Tensor:
        """Expose scheduler index for PoC assertions/telemetry without owning it."""
        return self.scheduler.current_action_index

    @property
    def env_requires_new_chunk(self) -> torch.Tensor:
        """Expose scheduler fetch state for PoC assertions/telemetry."""
        return self.scheduler.env_requires_new_chunk
