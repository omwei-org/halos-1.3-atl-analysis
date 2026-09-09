# Invariant Matrix

## Purpose

This document is the authoritative invariant map for the current Halos / GIE / Commit Gate proof-of-concept. It defines what must remain true across the execution path before test coverage is revised.

The matrix is deliberately broader than a test inventory. Some invariants are directly executable in the PoC; others are architectural or production-hardware requirements that the PoC can only document or partially demonstrate.

## Reference execution model

```text
AI / robot policy
      |
      v
 proposed execution object
      |
      v
     SLC  ---- execution evidence
      |              |
      v              v
     GIE -------- authority
      |              |
      +-------+------+ 
              |
          Commit Gate
              ^
              |
            Halos
           safety
              |
              v
        SDM / ATL boundary
              |
              v
        physical effect
```

The Commit Gate does not establish authority or safety. It enforces their conjunction at the execution boundary.

> Authority cannot override safety. Safety cannot override authority.

## Status

- **GREEN** — directly enforced and covered by the current PoC/tests.
- **YELLOW** — partially enforced, structurally guaranteed, or missing a dedicated test.
- **RED** — required invariant currently not demonstrated by the PoC.
- **ARCHITECTURAL** — intentional production/hardware property outside the current PoC execution model.

## Matrix

| ID | Invariant | Enforcement point | Evidence / observability | Current status | Next action |
|---|---|---|---|---|---|
| I-01 | Execution evidence is not authority. | GIE | Evidence-bound check; authority remains GIE-owned. | GREEN | Keep negative test. |
| I-02 | Authority originates only from GIE-owned state. | GIE | GIE authority context/state. | GREEN | Add explicit architectural assertion/documentation. |
| I-03 | Explicit `AuthorityContext` cannot mutate GIE state. | GIE | State before/after explicit-context check. | GREEN | Preserve as intentional test/offline escape hatch. |
| I-04 | Every execution is bound to an `env_id`. | Path / GIE / Commit Gate | `env_id` carried through result and boundary. | GREEN | Migrate stale tests. |
| I-05 | Authority cannot cross environments. | Commit Gate / ATL | Authority result `env_id` mismatch. | GREEN | Keep cross-environment negative test. |
| I-06 | A concrete execution object has stable canonical identity. | Execution Identity | SHA-256 digest of canonical bytes. | GREEN | Keep generic identity tests. |
| I-07 | Any mutation of canonical execution bytes changes execution identity. | Execution Identity / Commit Gate | Digest comparison. | GREEN | Keep mutation test. |
| I-08 | Authority is bound to the exact execution digest. | Commit Gate | Authority digest == execution digest. | GREEN | Keep mismatch test. |
| I-09 | Safety is independently bound to the same execution digest. | Commit Gate | Safety digest == execution digest. | GREEN | Add explicit conjunction coverage if needed. |
| I-10 | `ALLOW = authority AND safety` for the exact execution object. | Commit Gate | Final `CommitDecision`. | GREEN | Keep conjunction tests. |
| I-11 | Authority BLOCK cannot be converted to ALLOW by safety ALLOW. | Commit Gate | BLOCK result. | GREEN | Keep negative test. |
| I-12 | A cached/stale execution epoch cannot execute after authority changes. | GIE / Commit Gate | `action_epoch` vs current authority epoch. | GREEN | Keep replay test. |
| I-13 | Revocation invalidates previously authorized execution. | GIE | Epoch change / revalidation. | GREEN | Keep revocation test. |
| I-14 | Reauthorization creates a new valid epoch. | GIE | New authority epoch accepted. | GREEN | Verify positive reauthorization case. |
| I-15 | Authority is revalidated immediately before final commit. | Governed Execution Path | Commit-time revalidation. | GREEN | Keep TOCTOU test. |
| I-16 | `command.env_id != path.env_id` is rejected before authority resolution. | Execution Path | `execution_env_mismatch`. | GREEN | Keep dedicated path test. |
| I-17 | The SDM packet is opaque to Equinibrium. | SDM adapter | Byte-preserving adapter; no field interpretation. | YELLOW | Add explicit non-interpretation/opaque-payload test or structural assertion. |
| I-18 | SDM → ATL preserves the exact original bytes. | SDM / ATL | Packet equality. | GREEN | Migrate stale SDM tests. |
| I-19 | ATL execution object contains exactly 64-byte packet data. | ATL boundary | Constructor validation. | GREEN | Keep length test. |
| I-20 | ALLOW forwards the exact original packet unchanged. | ATL boundary | Returned/transmitted bytes equality. | GREEN | Keep exact-byte test. |
| I-21 | BLOCK produces zero downstream payload. | ATL boundary | `None` / no transmission. | GREEN | Keep block test. |
| I-22 | Governance epoch mismatch blocks even when packet bytes are identical. | ATL / Commit Gate | Epoch mismatch. | GREEN | Keep replay test. |
| I-23 | Packet mutation after authority binding blocks. | SDM / ATL / Commit Gate | Digest mismatch. | GREEN | Keep mutation test. |
| I-24 | A cross-environment execution object cannot inherit authority. | ATL / Commit Gate | Environment mismatch. | GREEN | Keep environment isolation test. |
| I-25 | Safety BLOCK blocks execution even with valid authority. | Commit Gate / Path | Final BLOCK decision. | GREEN | Keep safety negative test. |
| I-26 | Authority BLOCK blocks execution even with safety ALLOW. | Commit Gate | Final BLOCK decision. | GREEN | Keep authority negative test. |
| I-27 | Acceptance by an upstream receiver is not execution authority. | Architectural boundary | Receiver semantics are downstream of Commit Gate. | ARCHITECTURAL | Document; do not model receiver acceptance as authority. |
| I-28 | No software component outside the trusted governance boundary can force a protected physical effect. | Production GIE / hardware boundary | Hardware enforcement evidence. | ARCHITECTURAL | Production hardware design requirement. |
| I-29 | Authorization state and architectural effect are atomic/consistent at the hardware execution boundary. | Production GIE / Commit Gate | Hardware timing/retirement semantics. | ARCHITECTURAL | Hardware design and verification requirement. |
| I-30 | Reset invalidates stale execution evidence. | Scheduler / integration layer | Reset epoch/state transition. | YELLOW | Add dedicated scheduler reset test. |
| I-31 | Reset does not create authority. | Scheduler / GIE | Authority state before/after reset. | RED | Add negative test. |
| I-32 | BLOCK does not require stopping upstream inference. | Scheduler | Inference continues after blocked execution. | RED | Add integration test. |
| I-33 | BLOCK produces a safe hold action where the integration contract requires one. | Scheduler / actuator adapter | Hold action from current state. | YELLOW | Add explicit test. |
| I-34 | Enforcement occurs per action, not only when a cached chunk is fetched. | Scheduler | Per-action authority epoch check. | RED | Add stale-action-in-chunk test. |
| I-35 | Scheduler/execution metadata is evidence only; scheduler cannot inject authority. | Scheduler → GIE | GIE-owned authority state remains authoritative. | YELLOW | Add dedicated negative test. |
| I-36 | Equinibrium does not parse, rewrite, or regenerate ATL packet fields. | SDM / ATL | Opaque byte path and exact-byte equality. | YELLOW | Add structural/code-level guarantee. |

## Reference scenario: Peer Robotics Peer3000

A concrete Physical AI reference scenario is the Peer Robotics autonomous pallet-handling workflow described publicly by Peer Robotics in its trailer-unloading use case. The scenario is useful because the robot performs physical work in a variable environment while NVIDIA Halos addresses functional-safety concerns.

The purpose here is **not** to reproduce or claim knowledge of Peer Robotics' private internal software architecture. The public workflow is used as an illustrative execution scenario onto which the Equinibrium governance boundary can be mapped.

### Demonstration model

```text
Peer3000 perception / policy
          |
          v
   proposed pallet action
          |
          v
         SLC
   semantic execution evidence
          |
          v
         GIE
   authority for this action
          |
          +-------------------+
          |                   |
          v                   v
       NVIDIA Halos       execution identity
        safety result      exact action bytes
          |                   |
          +---------+---------+
                    v
               Commit Gate
                    |
             +------+------+
             |             |
           ALLOW          BLOCK
             |             |
             v             v
       SDM / ATL       no physical
       exact bytes       effect
```

### Example A — safety ALLOW, authority BLOCK

A pallet movement can remain physically safe according to the independent safety layer while the authorization epoch has changed. For example, a previously cached action may carry `action_epoch = 481` while GIE has already moved to `authority_epoch = 482`.

```text
HALOS  = ALLOW
GIE    = BLOCK   (stale / revoked authority)
COMMIT = BLOCK
```

The robot may continue perception and planning; the stale physical action does not cross the execution boundary.

### Example B — authority ALLOW, safety BLOCK

The action may be authorized for the robot's mission while the safety layer independently detects an unsafe physical condition, such as a person entering the relevant trajectory.

```text
GIE    = ALLOW
HALOS  = BLOCK
COMMIT = BLOCK
```

Authority therefore cannot override safety.

### Example C — both ALLOW

```text
GIE    = ALLOW
HALOS  = ALLOW
DIGEST = MATCH
EPOCH  = CURRENT
COMMIT = ALLOW
```

Only then is the exact execution object eligible to cross the protected boundary.

## PoC demonstrability

The Peer3000 scenario is not merely a future conceptual example. The **logic of the scenario can already be demonstrated by the current PoC**, even though the PoC is not a physical Peer3000 integration.

The current PoC already models the essential control sequence:

1. create a concrete execution object;
2. derive a stable execution digest;
3. resolve authority from GIE-owned state;
4. bind safety independently to the same execution identity;
5. revalidate authority immediately before commit;
6. enforce `authority AND safety` at Commit Gate;
7. preserve exact bytes through SDM/ATL;
8. produce no downstream payload on BLOCK.

The remaining gap is therefore **integration realism**, not the core governance principle. A future demo can replace the synthetic execution object with a robot action representation while preserving the same invariant set.

## Architectural boundary

The central contract remains:

> **Evidence may travel through the execution pipeline. Authority may not.**

SLC provides semantic/execution evidence. GIE resolves authority. NVIDIA Halos provides an independent safety decision. Commit Gate enforces their conjunction against one exact execution identity. The downstream receiver does not become an authority source merely because it accepts a packet.

## Test strategy after matrix review

The next test pass should be driven by this matrix rather than by adding more variants of already-covered checks.

Priority order:

1. migrate stale SDM/ATL tests to the explicit `env_id` contract;
2. map every existing `poc/test_*.py` test to one or more invariant IDs;
3. remove duplicate/obsolete tests only after the mapping is explicit;
4. add missing scheduler tests for I-30 through I-35;
5. add explicit opaque-packet / no-rewrite coverage for I-17 and I-36;
6. leave I-27 through I-29 explicitly marked as architectural / production-hardware requirements rather than pretending the PoC proves them.
