from __future__ import annotations

import torch

from isaaclab_arena.policy.action_scheduling.action_chunk_scheduler import ActionChunkScheduler
from poc.gie import GIE
from poc.gie_action_chunk_scheduler import GIEActionChunkScheduler


def make_scheduler(num_envs: int = 1, chunk_length: int = 5, action_dim: int = 4):
    return ActionChunkScheduler(
        num_envs=num_envs,
        action_chunk_length=chunk_length,
        action_horizon=chunk_length,
        action_dim=action_dim,
        device="cpu",
    )


def test_mid_chunk_revoke_blocks_remaining_cached_actions():
    gie = GIE()
    assert gie.grant(0) == 1

    scheduler = GIEActionChunkScheduler(make_scheduler(), gie)
    chunk = torch.arange(20, dtype=torch.float32).reshape(1, 5, 4)

    def fetch():
        return chunk.clone()

    for i in range(3):
        action = scheduler.get_action(fetch)
        assert torch.equal(action[0], chunk[0, i])

    gie.revoke(0)

    for i in range(3, 5):
        action = scheduler.get_action(fetch)
        assert torch.equal(action[0], chunk[0, 2]), f"index {i} leaked"

    assert scheduler.blocked_actions == 2
    assert scheduler.block_reasons == {"revoked": 2}


def test_epoch_change_blocks_old_cached_chunk_until_refetch():
    gie = GIE()
    assert gie.grant(0) == 1

    scheduler = GIEActionChunkScheduler(make_scheduler(), gie)
    chunk = torch.arange(20, dtype=torch.float32).reshape(1, 5, 4)

    assert torch.equal(scheduler.get_action(fetch := lambda: chunk.clone())[0], chunk[0, 0])
    assert gie.grant(0) == 2

    action = scheduler.get_action(fetch)
    assert torch.equal(action[0], chunk[0, 0])
    assert scheduler.block_reasons["epoch_mismatch"] == 1

    for _ in range(3):
        scheduler.get_action(fetch)

    assert scheduler.block_reasons["epoch_mismatch"] == 4

    action = scheduler.get_action(fetch)
    assert torch.equal(action[0], chunk[0, 0])
    assert scheduler.allowed_actions == 2


def test_block_does_not_stop_upstream_inference():
    """I-32: blocked execution does not stop upstream inference/fetching."""
    gie = GIE()
    gie.grant(0)
    scheduler = GIEActionChunkScheduler(make_scheduler(), gie)
    chunk = torch.arange(20, dtype=torch.float32).reshape(1, 5, 4)
    inference_calls = 0

    def fetch():
        nonlocal inference_calls
        inference_calls += 1
        return chunk.clone()

    scheduler.get_action(fetch)
    gie.revoke(0)

    # The cached actions are blocked, but the scheduler continues consuming them.
    scheduler.get_action(fetch)
    scheduler.get_action(fetch)

    assert inference_calls == 1
    assert scheduler.blocked_actions == 2
    assert scheduler.current_action_index.item() == 3


def test_reset_during_revoke_does_not_grant_authority():
    gie = GIE()
    gie.grant(0)

    scheduler = GIEActionChunkScheduler(make_scheduler(), gie)
    chunk = torch.ones((1, 5, 4), dtype=torch.float32)

    def fetch():
        return chunk.clone()

    scheduler.get_action(fetch)
    gie.revoke(0)
    scheduler.reset(torch.tensor([0]))

    action = scheduler.get_action(fetch)
    assert torch.equal(action[0], chunk[0, 0])
    assert scheduler.block_reasons["revoked"] == 1
    assert scheduler.action_epoch[0].item() == 1


def test_multi_env_authority_is_independent():
    gie = GIE()
    assert gie.grant(0) == 1
    assert gie.grant(1) == 1

    scheduler = GIEActionChunkScheduler(make_scheduler(num_envs=2), gie)
    chunk = torch.arange(40, dtype=torch.float32).reshape(2, 5, 4)

    def fetch():
        return chunk.clone()

    action = scheduler.get_action(fetch)
    assert torch.equal(action[0], chunk[0, 0])
    assert torch.equal(action[1], chunk[1, 0])

    gie.revoke(0)

    action = scheduler.get_action(fetch)
    assert torch.equal(action[0], chunk[0, 0])
    assert torch.equal(action[1], chunk[1, 1])

    assert scheduler.blocked_actions == 1
    assert scheduler.allowed_actions == 3


def test_hold_action_overrides_last_authorized():
    gie = GIE()
    gie.grant(0)

    scheduler = GIEActionChunkScheduler(make_scheduler(), gie)
    chunk = torch.arange(20, dtype=torch.float32).reshape(1, 5, 4)
    hold = torch.full((1, 4), 99.0)

    def fetch():
        return chunk.clone()

    scheduler.get_action(fetch)
    gie.revoke(0)

    action = scheduler.get_action(fetch, hold_action=hold)
    assert torch.equal(action[0], hold[0])


def test_no_authority_blocks_initial_fetch_output():
    gie = GIE()
    scheduler = GIEActionChunkScheduler(make_scheduler(), gie)
    chunk = torch.arange(20, dtype=torch.float32).reshape(1, 5, 4)

    def fetch():
        return chunk.clone()

    action = scheduler.get_action(fetch)
    assert torch.equal(action[0], torch.zeros(4))
    assert scheduler.blocked_actions == 1
    assert scheduler.block_reasons["no_authority_context"] == 1


def test_scheduler_state_is_owned_by_real_scheduler():
    gie = GIE()
    gie.grant(0)
    real_scheduler = make_scheduler()
    wrapper = GIEActionChunkScheduler(real_scheduler, gie)

    chunk = torch.arange(20, dtype=torch.float32).reshape(1, 5, 4)

    def fetch():
        return chunk.clone()

    wrapper.get_action(fetch)
    assert real_scheduler.current_action_index.item() == 1
    assert wrapper.current_action_index is real_scheduler.current_action_index
    assert wrapper.env_requires_new_chunk is real_scheduler.env_requires_new_chunk


if __name__ == "__main__":
    raise SystemExit("Run with pytest: pytest poc/test_gie_scheduler.py")
