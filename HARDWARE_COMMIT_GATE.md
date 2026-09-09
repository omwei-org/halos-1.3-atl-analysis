# Hardware Commit Gate

## Purpose

This document defines the next engineering boundary after the invariant-complete software PoC: a hardware-enforced execution boundary in which authorization and safety are evaluated as independent inputs and their conjunction controls the architectural effect.

The design deliberately does **not** move authority into Halos, does **not** turn the receiver into an authority source, and does **not** require Equinibrium to reinterpret the ATL command packet.

## 1. Core property

The production boundary must implement:

```text
COMMIT = AUTHORITY_ALLOW
       AND SAFETY_ALLOW
       AND ENV_MATCH
       AND EPOCH_CURRENT
       AND IDENTITY_MATCH
```

The critical distinction is between **decision generation** and **decision enforcement**:

- GIE generates the authority decision.
- NVIDIA Halos generates the independent safety decision.
- The Commit Gate enforces the conjunction.
- The downstream receiver only consumes an already-authorized command.
- No downstream acceptance event creates or extends authority.

## 2. Proposed hardware position

The preferred insertion point is immediately before the protected architectural effect / command receiver:

```text
                 AI / autonomy stack
                         |
                         v
                  proposed action
                         |
                 +-------+-------+
                 |               |
                 v               v
                GIE            Halos
             authority          safety
                 |               |
                 +-------+-------+
                         |
                         v
                 +---------------+
                 | COMMIT GATE   |
                 |               |
                 | env match     |
                 | epoch match   |
                 | digest match  |
                 | auth AND safe |
                 +-------+-------+
                         |
                   ALLOW | BLOCK
                         |
                         v
                    SDM / ATL
                         |
                         v
                 command receiver
                         |
                         v
                  physical effect
```

For the Halos ATL integration, the software boundary remains:

```text
SDM exact 64-byte packet
        |
        v
Equinibrium Commit Gate
        |
   exact bytes
        v
ATL command receiver
```

The hardware implementation should preserve this semantic boundary rather than introducing an Equinibrium-specific command parser.

## 3. Authority is state, not payload

The strongest production invariant is:

> **Authority is not carried by the execution object.**

The execution object carries evidence such as:

- environment identifier;
- execution epoch;
- exact execution identity / digest.

Authority is maintained in trusted governance state. The execution pipeline cannot manufacture an `AuthorityContext` and inject it into the Commit Gate.

A hardware implementation should therefore expose only a narrow authority interface, for example:

```text
GIE trusted state
    |
    +--> current_authority_epoch
    +--> authority_valid
    +--> authority_env
```

The exact encoding is implementation-specific. The architectural rule is not.

## 4. Safety is independent

Halos remains the independent safety authority for the safety dimension.

The Commit Gate must not reinterpret the meaning of a Halos safety result. It consumes a bounded safety decision associated with the same execution identity.

Therefore:

```text
GIE    = BLOCK, Halos = ALLOW  -> BLOCK
GIE    = ALLOW, Halos = BLOCK  -> BLOCK
GIE    = ALLOW, Halos = ALLOW  -> candidate for COMMIT
```

The final case still requires identity, environment and epoch consistency.

## 5. Execution identity

The Commit Gate must bind the decision to the exact object whose architectural effect is being authorized.

For byte-oriented command paths this means:

```text
execution_digest = HASH(exact command bytes)
```

Any mutation between authorization and the protected boundary must invalidate the binding.

The hardware does not need to understand the semantic fields of an ATL packet to enforce this property. It needs only a deterministic identity mechanism over the protected execution representation.

This preserves I-17 and I-36: opaque packet handling and no command-field rewriting remain valid at the Equinibrium boundary.

## 6. Epoch / revocation semantics

The hardware boundary must distinguish three states:

```text
VALID(current epoch)     -> may commit
STALE(old epoch)         -> must block
REVOKED(current epoch)   -> must block
```

A new grant creates a new authority epoch. A cached execution carrying the previous epoch cannot become valid merely because its bytes remain unchanged.

The important property is that revocation is effective at the execution boundary, not only at action generation time.

## 7. Atomicity requirement

I-29 is the first invariant that the software PoC intentionally does not prove.

Production hardware must make the relationship between governance state and architectural effect explicit:

```text
              governance state
                     |
             sample / validate
                     |
                COMMIT decision
                     |
            architectural effect
```

The implementation must prevent an execution from being architecturally committed using an authorization state that was valid only before the final governance check.

This is a hardware timing / retirement problem, not merely an API problem.

A candidate implementation therefore needs a precisely defined point at which:

1. execution identity is fixed;
2. authority state is sampled;
3. safety state is sampled;
4. all predicates are evaluated;
5. the effect is either committed or suppressed.

## 8. No software bypass

I-28 requires the protected effect to sit behind the trusted enforcement boundary.

The desired property is:

```text
untrusted software ----X----> protected effect
                           
trusted Commit Gate --------> protected effect
```

Software may request an action, but once the action enters the protected execution boundary, software outside the trusted governance domain must not be able to force the effect without satisfying the Commit Gate predicates.

This is the point where the concept becomes materially different from a software policy check.

## 9. Minimal hardware state

A first implementation should resist adding unnecessary machinery. The minimum conceptual state is:

```text
GIE_STATE
  authority_valid
  authority_epoch
  authority_env

EXEC_STATE
  execution_env
  execution_epoch
  execution_digest

SAFETY_STATE
  safety_valid
  safety_digest

COMMIT
  allow = all required predicates
```

Additional trace, recovery, telemetry and attestation functions can be layered around this core without changing the fundamental enforcement rule.

## 10. Security properties to verify

The first RTL/formal verification target should be a small set of adversarial properties:

### P1 — authority cannot be forged

Changing execution metadata cannot create authority.

### P2 — stale epoch cannot commit

If `execution_epoch != authority_epoch`, the protected effect is suppressed.

### P3 — revocation wins

If `authority_valid = false`, the protected effect is suppressed regardless of safety ALLOW.

### P4 — safety wins independently

If safety is BLOCK, the protected effect is suppressed regardless of authority ALLOW.

### P5 — identity binding

If the execution digest changes after authorization, the protected effect is suppressed.

### P6 — environment isolation

Authority for environment A cannot authorize an execution belonging to environment B.

### P7 — no bypass

No untrusted control path can directly cause the protected effect while Commit Gate is BLOCK.

### P8 — positive commit

Only when every required predicate is valid may the protected effect be enabled.

## 11. What should *not* be implemented

The first hardware prototype should explicitly avoid:

- embedding a full policy engine into the Commit Gate;
- parsing ATL semantic fields at the Equinibrium boundary;
- regenerating CRCs or sequence counters;
- allowing the receiver to establish authority;
- accepting caller-provided authority context as trusted state;
- coupling the enforcement point to one particular robot or policy framework;
- requiring upstream inference to stop when execution is blocked.

These exclusions preserve the invariant-driven architecture established by the PoC.

## 12. Transition from PoC to RTL

The immediate engineering sequence is:

1. freeze the software invariant contract;
2. convert I-28 and I-29 into hardware-level properties;
3. define the trusted-state interface to GIE;
4. define the safety-result interface to Halos;
5. define the exact protected execution representation;
6. define the final commit point relative to instruction retirement / command transmission;
7. write a minimal RTL reference model;
8. express P1-P8 as assertions/formal properties;
9. run adversarial simulation against the same scenarios already covered by the Python PoC;
10. only then optimize or specialize for a target SoC.

## 13. Architectural claim

The resulting architecture can be summarized as:

> **GIE decides whether an execution is authorized. Halos decides whether it is safe. Commit Gate decides whether that exact execution may cross the protected execution boundary.**

Or more compactly:

> **Authority × Safety × Identity × Freshness = Commit eligibility.**

The final physical guarantee belongs to the hardware boundary, not to the policy engine and not to the downstream receiver.
