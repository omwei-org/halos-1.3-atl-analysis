# Test Matrix

## Purpose

This document maps the current `poc/test_*.py` suite to the invariant IDs in `INVARIANT_MATRIX.md`.

The goal is to distinguish **PRIMARY** evidence (the test directly proves the invariant), **SECONDARY** evidence (the test exercises the same property indirectly or at another boundary), **DUPLICATE** coverage (useful but materially overlapping with a stronger primary test), and **MISSING** coverage.

This is an audit artifact only. **No test or implementation changes are made by this matrix.**

## Legend

- **PRIMARY** — direct, minimal evidence for the invariant.
- **SECONDARY** — supports the invariant, but another test is the clearer proof.
- **DUPLICATE** — substantially overlaps existing primary evidence; do not add another variant merely for count.
- **MISSING** — no current test directly demonstrates the invariant.
- **STALE** — test concept is valid but the current source no longer matches the API contract and must be migrated before it can count as executable evidence.

## Invariant → test mapping

| Invariant | PRIMARY | SECONDARY | DUPLICATE / overlap | MISSING / issue |
|---|---|---|---|---|
| I-01 | `test_h1_generated_does_not_imply_authority` | `test_byte_execution_identity_is_non_authoritative_evidence` | — | — |
| I-02 | `test_h1_generated_does_not_imply_authority` | `test_explicit_context_can_be_checked_without_mutating_gie_state` | — | Explicit architectural assertion could improve readability. |
| I-03 | `test_explicit_context_can_be_checked_without_mutating_gie_state` | — | — | — |
| I-04 | `test_cross_environment_authority_cannot_cross_atl_boundary` | `test_multi_env_authority_is_independent`, governed-path env mismatch test | — | — |
| I-05 | `test_authority_from_different_environment_cannot_commit` | `test_cross_environment_authority_cannot_cross_atl_boundary` | — | — |
| I-06 | `test_execution_identity` suite | `test_byte_execution_identity_is_non_authoritative_evidence` | — | — |
| I-07 | `test_execution_identity` mutation coverage | `test_wrong_packet_identity_cannot_cross_boundary` | — | — |
| I-08 | `test_safety_for_different_action_cannot_commit` is safety-side; authority-side digest mismatch is in ATL/path coverage | `test_wrong_packet_identity_cannot_cross_boundary` | Some digest mismatch cases overlap | Confirm one direct authority-digest mismatch test remains after full audit. |
| I-09 | `test_safety_for_different_action_cannot_commit` | Halos adapter digest mismatch test | — | — |
| I-10 | `test_authority_and_safety_allow_commits_same_action` | governed path positive test | — | — |
| I-11 | `test_commit_gate_does_not_convert_safety_into_authority` | `test_authority_block_prevents_commit_even_when_safe` | — | — |
| I-12 | `test_reauthorization_creates_new_epoch` | scheduler cached-chunk epoch test; ATL replay test | — | — |
| I-13 | `test_h2_per_action_check_observes_current_authority` | `test_mid_chunk_revoke_blocks_remaining_cached_actions` | — | — |
| I-14 | `test_reauthorization_creates_new_epoch` | scheduler refetch after epoch change | — | — |
| I-15 | `test_stale_allow_cannot_cross_commit_after_revocation` | governed-path commit revalidation test | — | — |
| I-16 | governed-path environment mismatch test | — | — | — |
| I-17 | — | `test_sdm_allowed_packet_reaches_receiver_byte_for_byte` | SDM exact-byte tests overlap | **MISSING dedicated opaque/non-interpretation assertion.** |
| I-18 | `test_sdm_allowed_packet_reaches_receiver_byte_for_byte` (STALE API) | ATL exact-byte test | — | **Migrate stale `SDMCommand` constructor.** |
| I-19 | `test_atl_packet_must_be_exactly_64_bytes` | — | — | — |
| I-20 | `test_allow_forwards_exact_original_atl_packet` | SDM receiver byte-for-byte test (STALE API) | — | — |
| I-21 | `test_block_emits_no_downstream_transmit_payload` | SDM replay/block test (STALE API) | — | — |
| I-22 | `test_same_packet_is_not_authorized_after_governance_epoch_change` | SDM replay after reauthorization (STALE API) | — | — |
| I-23 | `test_wrong_packet_identity_cannot_cross_boundary` | SDM packet mutation test (STALE API) | — | — |
| I-24 | `test_cross_environment_authority_cannot_cross_atl_boundary` | governed-path multi-env test | — | — |
| I-25 | `test_safety_block_prevents_commit_even_when_authorized` | Halos adapter safety BLOCK test; governed path safety test | — | — |
| I-26 | `test_authority_block_prevents_commit_even_when_safe` | `test_commit_gate_does_not_convert_safety_into_authority` | — | — |
| I-27 | — | receiver tests show receiver is downstream only | — | Architectural documentation only; intentionally not executable. |
| I-28 | — | — | — | Architectural / production hardware requirement. |
| I-29 | — | — | — | Architectural / production hardware requirement. |
| I-30 | `test_reset_during_revoke_does_not_grant_authority` | scheduler reset state assertions | — | Matrix status should be updated from YELLOW if this remains stable. |
| I-31 | `test_reset_during_revoke_does_not_grant_authority` | `test_no_authority_blocks_initial_fetch_output` | — | Matrix status should be updated from RED. |
| I-32 | — | — | — | **MISSING:** explicit proof that upstream inference continues after BLOCK. |
| I-33 | `test_hold_action_overrides_last_authorized` | `test_reset_during_revoke_does_not_grant_authority` | — | Matrix status should be updated from YELLOW if hold behavior is contractual. |
| I-34 | `test_epoch_change_blocks_old_cached_chunk_until_refetch` | `test_mid_chunk_revoke_blocks_remaining_cached_actions` | — | Matrix status should be updated from RED. |
| I-35 | `test_h1_generated_does_not_imply_authority` / arena-security suite | scheduler authority isolation behavior | — | Add a scheduler-specific negative test only if needed to make the boundary explicit. |
| I-36 | — | `test_allow_forwards_exact_original_atl_packet` | I-18/I-20 overlap | **MISSING explicit structural/code-level no-parse/no-rewrite guarantee.** |

## Test-file inventory

### `poc/test_gie.py`

Primary authority semantics: I-01, I-02, I-03, I-12, I-13, I-14, with byte-evidence support for I-06/I-08/I-35.

The explicit `AuthorityContext` test is intentionally retained. It demonstrates that the offline/test escape hatch does not mutate GIE-owned state; it does **not** mean the execution pipeline is allowed to inject authority.

### `poc/test_gie_arena_security.py`

Primary/secondary authority-boundary evidence: I-01, I-02, I-03, I-31, I-35. This is the strongest integration-level negative evidence that Arena metadata/evidence cannot become GIE authority.

### `poc/test_gie_scheduler.py`

This is currently the strongest scheduler file. It directly covers I-30, I-31, I-33 and I-34, plus multi-environment independence and hold behavior. In particular, `test_epoch_change_blocks_old_cached_chunk_until_refetch` proves that cached actions are re-evaluated after authority changes rather than being authorized only when a chunk is fetched.

### `poc/test_execution_identity.py`

Primary evidence for I-06 and I-07.

### `poc/test_commit_gate.py`

Primary evidence for I-05, I-08/I-09 digest binding, I-10, I-11, I-25 and I-26. This file should not be expanded with redundant conjunction variants unless a new invariant requires them.

### `poc/test_commit_boundary.py`

Primary evidence for I-15 / TOCTOU revalidation. **Currently stale:** its calls use the old `CommitGate.commit(action_digest, authority, safety)` signature rather than the current `commit(env_id, action_digest, authority, safety)` contract. The conceptual tests are still valuable and should be migrated, not redesigned.

### `poc/test_halos_adapter.py`

Primary/secondary evidence for I-09, I-10, I-11, I-25 and I-26. It verifies that Halos is an independent safety input rather than an authority source.

### `poc/test_atl_boundary.py`

Primary evidence for I-19, I-20, I-21, I-22, I-23 and I-24. This is the current canonical ATL-boundary test layer.

### `poc/test_sdm_boundary.py`

Conceptually important for I-17, I-18, I-21, I-22 and I-23, but **STALE** because current `SDMCommand` requires `env_id`. These tests should be migrated to the explicit environment-bound contract before being counted as passing evidence.

### `poc/test_governed_sdm_path.py`

Primary integration evidence for I-04, I-05, I-15, I-16, I-18, I-22, I-24 and I-25. This is the canonical composed execution-path test layer.

### `poc/test_end_to_end_atl.py`

Conceptually covers I-18, I-20, I-21 and I-22, but is **STALE** for the same explicit-`env_id` contract migration as `test_sdm_boundary.py`. Treat as migration work, not new architecture.

## Conclusions from the audit

1. **The core governance model is not test-empty.** I-01 through I-16 and I-19 through I-26 have substantial direct coverage.
2. **Scheduler coverage is stronger than the invariant matrix originally indicated.** I-30, I-31, I-33 and I-34 are already directly exercised; their matrix statuses should be corrected after this audit.
3. **The actual executable gaps are narrow:** I-17, I-32 and I-36, plus any missing direct authority-digest mismatch assertion for I-08 after the full suite is run.
4. **There are stale tests, not stale architecture:** `test_sdm_boundary.py`, `test_end_to_end_atl.py`, and `test_commit_boundary.py` need API migration to the current explicit `env_id` contract.
5. **Do not redirect the PoC toward Peer Robotics.** Peer3000 remains a reference scenario only; the implementation remains invariant-driven.
6. **Do not add redundant tests merely to increase count.** The next code changes should be limited to migration of stale tests and targeted coverage for the genuinely missing invariants.

## Next implementation order

1. Migrate `test_commit_boundary.py` to `CommitGate.commit(env_id, ...)`.
2. Migrate `test_sdm_boundary.py` and `test_end_to_end_atl.py` to `SDMCommand(env_id, ...)` / `ATLExecutionObject(env_id, ...)`.
3. Run the complete test suite and use failures to identify any additional API drift.
4. Add only the genuinely missing tests: I-17, I-32 and I-36, plus a direct I-08 authority-digest mismatch test if the full audit confirms it is absent.
5. Update `INVARIANT_MATRIX.md` statuses from the audited evidence rather than before it.
