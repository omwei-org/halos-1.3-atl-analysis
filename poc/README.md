# Minimal GIE PoC

This directory contains the first policy-neutral execution-authority prototype for the GR00T/G1 experiment.

## Scope

v0.1 intentionally contains no dependency on GR00T, Isaac Lab, Isaac Sim, Arena, or G1.

The isolated contract tests establish the core authority semantics before integration:

- generated action without authority → `BLOCK`;
- currently authorized action → `ALLOW`;
- revocation blocks an already-generated/cached action epoch;
- re-authorization advances the epoch;
- explicit authority contexts can be checked without mutating GIE state.

## Files

- `gie.py` — minimal execution-authority contract;
- `test_gie.py` — isolated unit tests for H1–H3 and re-authorization.

## Run

From this directory:

```bash
python -m pytest -q
```

The next integration step will add the scheduler enforcement adapter and exercise H2/H3 against the real action-chunk replay path.
