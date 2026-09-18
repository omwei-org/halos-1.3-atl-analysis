# HALOS 1.3 — Execution Authority Analysis

Reference implementation and research environment for **Execution Authority** integrated with NVIDIA Halos 1.3 / Outside-In Safety Framework.

Maintained by **Equinibrium / OMWEI**.

## Purpose

This repository explores a distinct architectural layer between an autonomous controller's decision and the externally effective execution of that decision.

The central separation is:

- **Safety governance** determines what is safe or acceptable.
- **Execution Authority** determines whether a particular effect is authorized to become system state **now**.
- **Commit Gate / Magic Box** enforces that decision at the execution boundary.

The goal is to demonstrate this separation without requiring changes to the controller's decision loop.

## Architecture

```text
Autonomous Controller
        |
        v
     HALOS / Safety
        |
        v
       GIE
        |
        v
   Commit Gate
        |
        v
 Physical Execution
```

The execution boundary is deliberately independent of the controller's internal architecture.

## Magic Box PoC

The repository contains a hardware-agnostic execution-boundary PoC.

The execution contract is based on:

```text
ExecutionObject = {
    env_id,   // execution environment
    payload,  // exact opaque command bytes
    epoch     // governance / authority epoch
}
```

The Magic Box must not interpret, rewrite, normalize, reconstruct, mutate, or otherwise alter the payload.

See:

- [MAGIC_BOX_POC.md](MAGIC_BOX_POC.md)
- [GIE_SUMMARY.md](GIE_SUMMARY.md)
- [HARDWARE_COMMIT_GATE.md](HARDWARE_COMMIT_GATE.md)

## Execution Authority

The key invariant is that authority is enforced independently of the autonomous controller.

A governance epoch provides freshness semantics:

```text
current epoch  -> eligible for authorization
old epoch      -> STALE_EPOCH
current epoch + revoked authority -> REVOKED
```

Freshness is evaluated at authorization/commit time. Revocation therefore invalidates previously prepared execution objects without requiring the controller to stop its decision loop or clean up outstanding objects.

`STALE_EPOCH` has precedence over `REVOKED`.

## Zero-Effect BLOCK

A blocked execution must produce **zero physical effect**.

The repository therefore distinguishes:

```text
decision
   |
   v
authorization
   |
   +---- BLOCK ----> no actuator effect
   |
   +---- ALLOW ----> commit ----> execution
```

This is an execution-boundary property, not merely a policy or logging property.

## Evidence and Invariants

The research environment documents both architectural invariants and their test coverage.

Key references:

- [INVARIANT_MATRIX.md](INVARIANT_MATRIX.md)
- [TEST_MATRIX.md](TEST_MATRIX.md)
- [GIE_SUMMARY.md](GIE_SUMMARY.md)
- [HARDWARE_COMMIT_GATE.md](HARDWARE_COMMIT_GATE.md)
- [MAGIC_BOX_POC.md](MAGIC_BOX_POC.md)
- [GR00T_GIE_EXECUTION_AUTHORITY_MAPPING.md](GR00T_GIE_EXECUTION_AUTHORITY_MAPPING.md)

The evidence model focuses on making authorization, execution, and resulting effects independently observable and correlatable.

## NVIDIA Halos 1.3 Integration

The current work uses NVIDIA Halos 1.3 / Outside-In Safety Framework as a concrete integration environment.

The UDP/ATL path is a **software PoC boundary**. It is not presented as the final hardware security boundary.

The production-oriented research direction is the earliest execution/commit point at which the authority decision can be independently protected against bypass.

## Scope and Claim Discipline

This repository is a research and reference implementation environment.

It does **not** claim that:

- the current software PoC is a hardware-enforced security boundary;
- HALOS alone provides independent execution authority;
- a packet or transport boundary automatically constitutes a trusted commit boundary;
- the current implementation provides production-grade hardware isolation.

The purpose is to establish and test the architectural and semantic properties before mapping them onto a protected hardware implementation.

## Relationship to EABC

This repository is a concrete implementation and evidence environment contributing to the broader **Execution Authority Boundary Contract (EABC)** work.

EABC defines the implementation-independent contract for trustworthy execution authority boundaries.

See the open specification:

https://github.com/omwei-org/omwei-eabc

This repository is **not** the EABC specification itself.

The relationship is:

```text
EABC
  |
  +-- open boundary specification
  |
  +-- interoperability contract / profiles
          |
          +-- Magic Box / GIE reference implementation
          |
          +-- concrete autonomous-system integrations
```

## Current Research Direction

The current work focuses on:

1. independent execution authority;
2. complete mediation at the execution boundary;
3. governance-epoch freshness;
4. opaque execution payloads;
5. deterministic ALLOW / BLOCK semantics;
6. zero-effect blocking;
7. evidence integrity and correlation;
8. mapping the software PoC onto the earliest independently protected commit boundary.

## Status

Research / reference implementation.

The repository is intended to provide executable evidence for the architectural claims and a concrete basis for interoperability work under EABC.

## License

Copyright 2026 Equinibrium.

Licensed under the [Apache License, Version 2.0](LICENSE).
