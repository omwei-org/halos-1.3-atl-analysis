# COMMIT_BOUNDARY_ANALYSIS.md — Summary

## Key Finding

**The natural production GIE Commit Gate location is the architectural commit boundary (Candidate D): the earliest hardware-protected boundary at which the requested execution effect becomes architecturally effective.**

The exact physical realization is architecture-dependent. It may be a state transition, control-state update, transaction commit, instruction retirement, protected register update, or equivalent commit point. The analysis must not assume a specific Halos state-register implementation unless independently verified.

The NVIDIA Halos 1.3 source evidence now makes the upstream path more precise: the inspected examples expose SDM/ATL command generation, a PLC command socket, and a UDP command receiver that validates packets and manages software safe-state/release state. They do **not** expose the downstream PLC/actuator implementation or a direct physical execution primitive. Therefore the UDP receiver is a command-acceptance/software-state boundary, not a proven final execution boundary.

```
Halos Safety Path
        ↓
SDM / ATL execution request
        ↓
64-byte CmdPacket / PLC command path
        ↓
UDP command receiver
        ↓
command validation / software safety-state handling
        ↓
[downstream PLC / controller / execution layer]
        ↓
SLC / Governance Context
        ↓
╔══════════════════════════════════════╗
║      GIE COMMIT GATE (HW)            ║
║                                      ║
║  Check current governance context    ║
║  Check execution binding             ║
║  Check governance epoch / validity   ║
║  Check authority / revocation        ║
║  Check transition / commit validity  ║
╚══════════════════════════════════════╝
        ↓
COMMIT / BLOCK
        ↓
Architectural Effect
```

---

## Six Candidate Boundaries Evaluated

| # | Candidate | Location | Verdict | Reason |
|---|-----------|----------|---------|--------|
| A | Pre-SEI | Before safety decision | ❌ REJECT | Too early; overlaps safety reasoning |
| B | SDM→ATL | Packet transmission | ✓ GOOD PoC | Demonstrates governance gating, but protects transport rather than final effect |
| C | Receiver→Execute | After command acceptance, before downstream execution | ✓ BETTER | Closer to execution, but the inspected examples do not expose the downstream commit primitive |
| D | Architectural Commit | Earliest protected commit boundary | ✓✓✓ OPTIMAL | Protects the execution effect itself; strongest bypass resistance |
| E | Actuation | Physical output | ❌ PRIMARY REJECT | Too late; architectural state may already have changed |

---

## Why Candidate D Wins

### 1. It protects the right object

The fundamental protected object is **the requested execution effect**, not the UDP packet. A packet is only one representation of execution intent.

### 2. It is independent of Halos safety reasoning

Halos answers whether an action is considered safe. GIE answers whether the requested execution effect is currently authorized under governance state. These are orthogonal properties.

### 3. It is bypass-resistant

A compromised component above the gate may generate or request an unauthorized execution effect, but cannot make the protected architectural effect effective without passing the hardware gate.

### 4. It supports revocation

A previously valid request can become unauthorized after a governance epoch or authority change. The commit decision is evaluated against the current protected governance context rather than relying on an old packet-level decision.

### 5. It does not require a new processor

The GIE primitive is a protected authorization/commit mechanism integrated into the existing SoC or safety-control path. The exact implementation is architecture-specific.

---

## Direct NVIDIA Source Evidence — Boundary Refinement

The inspected NVIDIA Halos 1.3 development package provides direct evidence for the exposed command path.

### `atl_cmd_pkt.h`

The source defines a packed **64-byte `CmdPacket`** containing identifier, sequence, command, timestamps, CRC32 and two object records. It explicitly defines:

- `CMD_MUTE` as **“Allow Operation”**;
- `CMD_UNMUTE` as **“Prevent Operation”**;
- `CMD_HW_ERROR`;
- `CMD_SW_ERROR`;
- safe-release request/ack/denied commands.

The CRC covers the packet fields other than the CRC field itself. This establishes packet integrity validation, not execution authority.

### `ATLControl.cpp`

The SDM-side control logic constructs the command packet, records pending ACK state, and sends the packet through a configured **PLC command socket** using UDP. The source comments explicitly identify this as the PLC command path.

### `cmd_rx.cpp`

The UDP receiver performs:

1. exact packet-size validation;
2. expected-sender validation;
3. packet identifier validation;
4. CRC32 validation;
5. command whitelist validation;
6. heartbeat handling;
7. software safe-state / release handling;
8. ACK generation/transmission;
9. optional VST relay.

It also supports operator/script safe release through stdin/FIFO and a startup safe-release loop.

### What the inspected examples do **not** establish

The inspected examples do not expose a GPIO write, actuator driver, motor-control write, direct hardware-register update, or concrete PLC-driver implementation for the physical output.

Therefore the source-backed path is:

```text
SDM / ATLControl
      ↓
MUTE / UNMUTE / error / release command
      ↓
64-byte CmdPacket
      ↓
UDP / PLC command path
      ↓
ATL UDP receiver
      ↓
validated command acceptance
      ↓
software safe-state / release handling
      ↓
[downstream PLC / controller / execution implementation not exposed]
      ↓
architectural / physical effect
```

This is an **evidence boundary**, not a claim that the complete NVIDIA product has no downstream execution implementation.

Accordingly, `cmd_rx.cpp` must not be described as the physical execution boundary without additional evidence.

---

## Three Distinct Control Boundaries

The source evidence supports a clean separation:

### Safety Decision — Halos

> Is this action considered safe?

### Command Acceptance — Halos reference implementation

> Is this received command structurally valid and from the expected sender, and what software safety state should the receiver maintain?

### Architectural Commit — GIE

> Can this requested execution effect become system state?

This separation is important because command acceptance is not equivalent to execution authority, and neither is equivalent to physical actuation.

---

## Critical Correction: No Exact Packet-Digest Authority Binding

The previous PoC formulation used `SHA-256(packet)` as part of the authority decision. This is **not the production GIE binding model**.

The 64-byte Halos packet contains dynamic fields such as sequence/timing information and CRC. Binding authority to the exact digest of every packet is therefore unsuitable as a stable authority primitive for a continuous command stream.

The preferred model is to bind authority to a **trusted execution context**, for example:

```
Semantic Identity
      +
Execution Context
      +
Governance Epoch
      +
Authority Context
      +
Commit Intent
      ↓
Trusted Commit Context
```

A packet may carry or represent this information, but the production GIE trust anchor must not depend on a software-supplied packet hash alone.

---

## PoC vs. Production

### PoC — Candidate B

```
SDM → SLC Software Gate → ATL/UDP → Receiver
```

The PoC demonstrates:
- governance authority can be evaluated independently of Halos safety;
- authority revocation can prevent a command from being transmitted;
- the original packet can be preserved byte-for-byte;
- epoch-based policy can be demonstrated in software.

It does **not** demonstrate that an already-admitted command cannot later produce an unauthorized architectural effect.

### Production — Candidate D

```
Execution Request → GIE Commit Gate → Architectural Effect
```

The production architecture provides the actual hardware enforcement boundary: an unauthorized execution effect cannot become architecturally effective solely because an upstream software component produced a valid command.

**Relationship:** the PoC validates the governance concept; the hardware GIE validates enforcement at the protected commit boundary.

---

## Three Distinct Concepts

### Safety Decision — Halos

> Is this action considered safe?

Owner: Halos safety logic / SEI.

### Authority Decision — Equinibrium

> Is this execution request currently authorized in the governance context?

Owner: SLC/GIE governance architecture.

### Architectural Commit — GIE

> Can this requested execution effect become system state?

Owner: GIE hardware enforcement.

A useful conceptual condition is:

```
Halos Safety = PERMISSIVE
        AND
GIE Authority = AUTHORIZED
        AND
Commit Context = VALID
        ↓
Architectural Effect may commit
```

If authority is revoked or the commit context is invalid, GIE blocks the protected effect even when the upstream Halos decision remains permissive.

---

## Safe-State / Safe-Release Boundary

The Halos receiver source also makes an important distinction between **software safe-state indication** and **physical execution authority**.

`cmd_rx.cpp` maintains local state such as `console_latched_` and `safe_release_prompt_ready_`. These are receiver-side software state variables used for safe-state indication and operator release handling. The source does not establish them as hardware actuator enables.

Similarly, the SDM-side source contains PLC-authoritative safe-release logic and repeats restrictive commands while the safe-state condition is latched.

Therefore:

> **A software safe-state latch or release prompt is not itself the GIE enforcement primitive.**

GIE must remain at the protected execution/architectural commit boundary.

---

## Evidence Discipline

- **VERIFIED** — directly confirmed from accessible NVIDIA source/package material.
- **DOCUMENTED** — stated in NVIDIA documentation.
- **INFERRED** — reconstructed from documented interfaces and execution logic.
- **PROPOSED** — Equinibrium architecture.

Current classification:

- Halos packet structure, MUTE/UNMUTE semantics, CRC validation: **VERIFIED**.
- SDM/ATL PLC command socket and UDP transmission: **VERIFIED**.
- Receiver-side packet validation, command interpretation, software safe-state/release handling and ACK: **VERIFIED**.
- Receiver as a command-acceptance boundary rather than proven physical execution boundary: **INFERRED from direct source inspection**.
- Absence of exposed actuator/GPIO/register/PLC-driver implementation in the inspected examples: **VERIFIED within the inspected source scope**.
- Candidate B as software PoC insertion point: **PROPOSED**.
- Candidate D as production GIE enforcement boundary: **PROPOSED architectural conclusion**.
- Exact downstream NVIDIA PLC/actuator commit primitive: **NOT ESTABLISHED by the inspected source**.

Do not claim that `cmd_rx.cpp` directly drives a physical actuator unless additional evidence establishes that fact.

---

## Final Conclusion

The strongest and most defensible architecture is:

> **SLC provides semantic and governance authorization; GIE enforces that authorization at the earliest hardware-protected boundary at which the requested execution effect becomes architecturally effective.**

The NVIDIA Halos 1.3 source evidence strengthens this conclusion by clearly separating safety decision, command generation, command acceptance and the still-unexposed downstream execution layer.

The SDM→ATL/UDP boundary remains valuable for PoC integration, but it must not be presented as the final GIE enforcement point.

### Final principle

> **Halos answers whether an action is safe. SLC determines whether the execution request is semantically and contextually authorized. GIE enforces whether the resulting execution effect may become system state.**
