# Equinibrium GIE Commit Gate: Natural Hardware Boundary Analysis

**Objective:** Determine the most technically natural implementation boundary for an Equinibrium SLC/GIE Commit Gate integrated with NVIDIA Halos 1.3, while clearly separating the software PoC insertion point from the production hardware enforcement boundary.

**Evidence Discipline:** VERIFIED / DOCUMENTED / INFERRED / PROPOSED are maintained throughout. NVIDIA-internal implementation details are not asserted unless independently verified.

---

## 1. Halos Execution Chain — Evidence-Based Reconstruction

The following chain combines documented NVIDIA interfaces with direct inspection of the accessible Halos 1.3 development package and architectural inference. The later stages are intentionally described generically where the accessible source does not expose the downstream implementation.

### Stage 1: Perception Input

| Aspect | Status | Evidence |
|---|---|---|
| Role | DOCUMENTED | SIPP / perception integration functions described by NVIDIA |
| Data | DOCUMENTED | Sensor and system input |
| Processing | INFERRED | Perception aggregation/processing |
| Output | DOCUMENTED | Structured perception information |

### Stage 2: Perception Integration

| Aspect | Status | Evidence |
|---|---|---|
| Components | DOCUMENTED | SAIM and PCM are identified in NVIDIA documentation |
| Role | DOCUMENTED | Perception integration layer |
| Internal processing | INFERRED | Fusion, interpretation and safety-relevant perception processing |

### Stage 3: Safety Element Interface (SEI)

| Aspect | Status | Evidence |
|---|---|---|
| Role | DOCUMENTED | NVIDIA describes an authoritative permissive/restrictive safety decision |
| Output | DOCUMENTED | PERMISSIVE or RESTRICTIVE safety decision |
| Internal policy evaluation | INFERRED | Exact implementation is not asserted here |

**Key property:** SEI is the authoritative safety-judgment point. Safety judgment is not the same thing as execution authority.

### Stage 4: Semantic Decision Module (SDM)

| Aspect | Status | Evidence |
|---|---|---|
| Role | DOCUMENTED | NVIDIA describes SDM as converting the safety decision into an ATL command |
| Opcode selection | DOCUMENTED / INFERRED | Exact mapping depends on the documented Halos command set |
| Serialization | VERIFIED | Accessible `atl_cmd_pkt.h` defines a packed 64-byte command packet |

**Key property:** SDM turns the safety decision into an execution-request representation.

### Stage 5: SDM → ATL / PLC Command Transport — Current PoC Boundary

```
SDM / ATLControl
      ↓
SLC SOFTWARE GATE
      ↓
ATL / UDP / PLC command socket
      ↓
Command Receiver
```

**Status:** PROPOSED — Equinibrium software PoC insertion point.

Direct source inspection confirms that `ATLControl.cpp` constructs the command packet, records pending ACK state, and sends it through a configured PLC command socket using UDP. This makes the boundary a practical PoC insertion point, but it does not make the transport itself the final execution boundary.

### Critical correction: packet digest is not the authority primitive

An earlier formulation used `SHA-256(packet)` as part of the authority decision. That is **not** the production GIE model.

The 64-byte packet contains dynamic transport/protocol fields such as sequence/timing information and CRC. A digest of the complete packet therefore identifies an individual packet instance, not a stable execution-authority context for a continuous stream.

The production authority model should instead bind authority to a trusted execution context, such as:

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

A packet can carry or represent this context, but a software-supplied packet hash alone is not a sufficient trust anchor.

### Stage 6: ATL Command Receiver — Validated Command Acceptance / Software Safety-State Boundary

| Aspect | Status | Evidence |
|---|---|---|
| Role | VERIFIED | Direct inspection of accessible `cmd_rx.cpp` |
| Packet-size validation | VERIFIED | Receiver rejects packets that are not exactly `COMMAND_PACKET_SIZE` |
| Expected-sender validation | VERIFIED | Receiver checks the configured SDM sender endpoint |
| Identifier validation | VERIFIED | Receiver validates the ATL packet identifier |
| CRC validation | VERIFIED | Receiver validates the packet CRC |
| Command whitelist | VERIFIED | Receiver accepts only supported command values |
| Software safe-state handling | VERIFIED | Receiver maintains safe-release prompt/latch state for relevant commands |
| ACK generation | VERIFIED | Receiver constructs and sends a validated ACK packet |
| VST relay | VERIFIED | Decision commands may be relayed separately for display/visualization |

**Key property:** `cmd_rx.cpp` is a **validated command-acceptance and software safety-state boundary**. It is **not established by the inspected source as the physical or architectural execution boundary**.

The receiver's `console_latched_` and `safe_release_prompt_ready_` variables are receiver-side software state. They support indication/release handling; they are not established as hardware actuator-enable primitives.

### Stage 7: Downstream PLC / Controller / Execution Layer

**Status:** INFERRED — exact implementation not exposed by the inspected examples.

The accessible source confirms a PLC command path and receiver-side command handling, but does not expose a concrete PLC driver, actuator write, GPIO operation, direct hardware-register update, motor-control primitive, or equivalent physical execution implementation in the inspected example scope.

Therefore the correct evidence-based representation is:

```
validated command acceptance
        ↓
[downstream PLC / controller / execution implementation]
        ↓
architectural / physical effect
```

The bracketed layer is intentionally not assigned a specific NVIDIA implementation without additional evidence.

### Stage 8: Architectural Effect / Commit Boundary

**Status:** INFERRED as the architectural concept; exact Halos implementation is not independently verified.

The relevant security boundary is the earliest point at which the requested execution effect becomes architecturally effective — for example, a protected state transition, control-state update, transaction commit, instruction retirement, protected register update, or equivalent commit point.

This is **Candidate D** and is the proposed production GIE enforcement boundary.

### Stage 9: Physical Effect

**Status:** INFERRED / system-dependent.

Physical actuation occurs downstream of the architectural effect. It is too late for the primary governance commit boundary because protected system state may already have changed. A secondary physical interlock may be appropriate in a particular safety architecture, but it does not replace the primary GIE commit boundary.

---

## 2. Candidate Enforcement Boundaries

### Candidate A — Pre-SEI

**Verdict: REJECT.**

Too early. The gate would operate before the authoritative Halos safety decision and would either duplicate safety reasoning or interfere with perception/safety semantics.

### Candidate B — SDM → ATL / Command Transport

**Verdict: GOOD PoC, NOT FINAL GIE BOUNDARY.**

What it protects:
- packet transmission;
- software-level authority admission.

What direct source evidence supports:
- SDM/ATLControl creates the command packet;
- the command is sent through the configured PLC command socket;
- the receiver validates and interprets the command.

What it demonstrates:
- authority can be evaluated independently of Halos safety;
- governance revocation can prevent a command from being transmitted;
- byte-for-byte packet preservation is possible.

What it cannot guarantee:
- that a command already admitted downstream cannot produce an unauthorized architectural effect;
- that compromised downstream software cannot transform execution intent;
- hardware-enforced prevention of the final state change.

### Candidate C — Receiver → Execution

**Verdict: BETTER, BUT NOT FINAL.**

This is closer to execution semantics and can block a validated command before downstream execution. However, the accessible examples do not expose the downstream execution primitive, so Candidate C cannot be claimed as the verified physical or architectural boundary.

### Candidate D — Earliest Hardware-Protected Architectural Commit

**Verdict: OPTIMAL PRODUCTION GIE BOUNDARY.**

```
Execution Request
      ↓
Execution Logic
      ↓
GIE COMMIT GATE
      ↓
Architectural Effect
```

The gate evaluates whether the requested execution effect is authorized under the current trusted governance context.

The defining property is not a particular register write. It is:

> **GIE is enforced at the earliest hardware-protected boundary at which the requested execution effect becomes architecturally effective.**

Possible physical mechanisms include a gated state update, transaction commit authorization, protected control-state transition, instruction-retirement check, or equivalent architecture-specific mechanism.

### Candidate E — Physical Actuation

**Verdict: REJECT AS PRIMARY BOUNDARY.**

Too late. Architectural state may already have changed. A secondary actuation interlock may still be useful in a particular safety architecture, but it does not replace the primary GIE commit boundary.

---

## 3. Safety vs Authority vs Command Acceptance vs Architectural Effect

These are distinct properties:

### Safety Decision — Halos

> **Is this action considered safe?**

### Authority Decision — SLC / Governance

> **Is this execution request currently authorized in the governance context?**

### Command Acceptance — Halos reference implementation

> **Is this received command structurally valid and from the expected sender, and what software safety state should the receiver maintain?**

### Architectural Commit — GIE

> **Can this requested execution effect become system state?**

Conceptually:

```
Halos Safety = PERMISSIVE
        AND
GIE Authority = AUTHORIZED
        AND
Commit Context = VALID
        ↓
Architectural Effect may commit
```

If Halos is restrictive, the safety path must prevent the unsafe action according to Halos policy. If Halos remains permissive but governance authority is revoked, GIE must still be able to block the architectural effect.

**Command acceptance is neither safety authorization nor execution authority.** A structurally valid packet may be accepted by the receiver while the corresponding execution request is still unauthorized under the GIE governance context.

This orthogonality is central to the architecture.

---

## 4. Safe-State and Safe-Release Are Not the GIE Boundary

The Halos source contains explicit safe-state and safe-release behavior on both sides of the command path.

The receiver maintains software variables including `console_latched_` and `safe_release_prompt_ready_`. It also accepts an operator/script `release` action through stdin/FIFO and can issue a safe-release request to the last known sender.

The SDM-side control logic contains PLC-authoritative safe-release handling and repeats restrictive commands while the safe-state condition remains latched.

These mechanisms are important for the safety lifecycle, but they do **not** establish a hardware-enforced execution authority boundary.

The correct distinction is:

```
Safe-state latch / release
        ≠
Execution authority
        ≠
GIE architectural commit gate
```

Therefore a software safe-state latch must not be presented as the GIE primitive, and an operator release action must not be treated as equivalent to hardware authorization of an architectural commit.

---

## 5. What the Current PoC Proves

### PoC

```
SDM → SLC Software Gate → ATL/UDP → Receiver
```

The PoC can demonstrate:

1. Halos safety decision remains unchanged.
2. SLC can evaluate governance authority independently.
3. A governance epoch change can invalidate a previously authorized context.
4. The software gate can block forwarding.
5. A forwarded packet can remain byte-for-byte unchanged.
6. Receiver-side validation still operates normally on admitted packets.

### What it does NOT prove

It does not prove that a downstream component cannot transform or execute an already-admitted request in an unauthorized way.

It does not prove the location of the final NVIDIA architectural commit primitive, because that implementation is not exposed in the inspected source.

Therefore:

> **The software SLC gate is a proof-of-concept authority boundary; the hardware GIE Commit Gate is the proposed production enforcement boundary.**

---

## 6. Authority Binding Model

### Do not bind authority to an exact packet digest

The exact packet is a transport representation and may contain dynamic fields. Exact-digest binding is therefore unsuitable as the fundamental production authority primitive.

### Preferred model

Authority should be associated with a trusted execution context:

```
Semantic Identity
Execution Context
Governance Epoch
Authority Context
Commit Intent
        ↓
Trusted Commit Context
```

`semantic_id` identifies an operation; it does not by itself establish authorization.

Likewise, a software-provided `execution_id` is not automatically a trust anchor. Production binding must be structurally or cryptographically tied to the execution context recognized by the protected architecture.

---

## 7. Governance Epoch and Revocation

The conceptual rule is:

```
commit_request.epoch == current_epoch
```

An epoch transition invalidates authority associated with the previous epoch.

The exact implementation may use counters, sequence values, signed/cryptographically bound contexts, or another protected mechanism. `current_epoch` should not be writable by ordinary execution software; it must be controlled through the protected governance path.

This enables the important case:

```
Halos: PERMISSIVE
Packet: structurally valid
Receiver: accepts
Authority: stale/revoked
        ↓
GIE: BLOCK
        ↓
No protected architectural effect
```

The receiver's acceptance of the packet does not override the protected governance state.

---

## 8. GIE Commit Semantics

GIE is defined by a security property, not by a single circuit topology.

### Required property

If the authorization predicate is false, the protected architectural effect does not become effective.

Conceptually:

```
Commit Request
      ↓
┌───────────────────────────────┐
│       GIE COMMIT GATE         │
│                               │
│ governance context valid?     │
│ execution binding valid?      │
│ epoch current?                │
│ authority not revoked?        │
│ transition/intent valid?      │
└───────────────────────────────┘
      ↓
 COMMIT / BLOCK
```

Atomicity is a required architectural property: the authorization decision and the protected effect must correspond to a consistent governance/execution context. An implementation may use atomic snapshots, transactional semantics, serialized commit paths, gated updates, or equivalent mechanisms. A literal lock is not mandatory.

### Core invariant

> **A protected execution effect cannot become architecturally effective solely because an upstream component produced a valid command or because the action was judged safe.**

---

## 9. Bypass Resistance

A production GIE should provide the following properties:

| Attack | Required GIE property |
|---|---|
| Modify command | Commit context is revalidated/bound at protected boundary |
| Replay stale authorization | Epoch/context validity fails |
| Substitute execution context | Execution binding fails |
| Compromise receiver | Receiver remains upstream of GIE |
| Compromise SDM | Cannot directly force protected architectural effect |
| Revoke authority during operation | Commit checks current protected governance state |
| TOCTOU between check and effect | Authorization and effect share a consistent commit context |

Core invariant:

> **No software outside the trusted governance/commit boundary can unilaterally force a protected execution effect.**

---

## 10. Experimental Validation

### Experiment 1 — Authority Revocation

1. Halos produces a permissive decision.
2. An execution request is associated with governance epoch N.
3. Governance advances to epoch N+1.
4. The same or equivalent execution intent is presented again.
5. Upstream packet validation may still succeed.
6. GIE evaluates the current protected governance context.
7. The stale authorization is rejected.
8. The protected architectural effect remains unchanged.

This experiment demonstrates why the production enforcement point must be downstream of packet admission.

### Experiment 2 — Commit Atomicity

Construct a transition whose protected architectural representation consists of multiple coordinated updates. Demonstrate that the GIE decision applies to the complete commit operation rather than permitting a partially authorized architectural state.

The exact mechanism is architecture-specific and must not be inferred from the current Halos documentation.

### Experiment 3 — Safety Block vs Authority Block

Run two cases:

**Safety block:** Halos is restrictive and the safety mechanism prevents the unsafe action.

**Authority block:** Halos is permissive, but governance authority is revoked; GIE blocks the protected architectural effect.

The resulting evidence demonstrates that safety and execution authority are independent dimensions.

---

## 11. Trusted Boundary Model

### Above GIE

Perception, SAIM/PCM, SEI, SDM, ATL/transport, receiver and downstream execution logic are upstream of the final hardware enforcement boundary.

They may determine the requested execution effect, but they cannot unilaterally force the protected effect once GIE is correctly implemented.

### At GIE

The hardware gate evaluates the trusted execution/governance context and authorizes or blocks the protected architectural commit.

### Below GIE

The protected architectural effect and its downstream system-specific consequences are affected by the gate.

The exact downstream chain — PLC state, controller state, drivers, actuation — is architecture-specific and should not be presented as verified Halos implementation without source evidence.

---

## 12. Practical Implementation Constraints

### Source access

The currently accessible NVIDIA material documents the interfaces and command path and exposes portions of the reference implementation, but it does not expose all downstream Halos/PLC implementation sources. Additional restricted source may be required to identify the exact internal commit primitive.

Therefore, the current analysis should not claim that the GIE can simply be inserted into a specific Halos internal state-register write.

### Integration options for PoC

The software PoC can be implemented as a wrapper, proxy or equivalent controlled insertion point around the documented command transport boundary, subject to the actual deployment environment.

### Production integration

A production GIE requires identification of the target SoC / safety controller and its actual architectural commit mechanism. The integration must be deterministic, low-latency and suitable for the relevant safety/security assurance process.

No gate-area, transistor-count or latency estimate should be treated as established until a concrete target architecture is selected.

---

## 13. Evidence Classification Matrix

| Claim | Classification |
|---|---|
| Halos exposes PERMISSIVE / RESTRICTIVE safety semantics | DOCUMENTED |
| `atl_cmd_pkt.h` defines the 64-byte command packet | VERIFIED |
| MUTE means “Allow Operation” and UNMUTE means “Prevent Operation” in the inspected header | VERIFIED |
| Packet CRC provides integrity checking | VERIFIED |
| SDM/ATLControl sends commands through a configured PLC UDP socket | VERIFIED |
| `cmd_rx.cpp` validates size, sender, identifier, CRC and supported commands | VERIFIED |
| `cmd_rx.cpp` manages software safe-state/release state and ACKs | VERIFIED |
| VST relay is secondary to command handling | VERIFIED |
| Inspected examples do not expose a concrete actuator/GPIO/register/PLC-driver implementation | VERIFIED within inspected source scope |
| Receiver is a command-acceptance/software-state boundary | INFERRED from direct source inspection |
| Exact downstream physical execution primitive | NOT ESTABLISHED |
| SDM→ATL/UDP as software PoC insertion point | PROPOSED |
| Architectural commit as production GIE boundary | PROPOSED architectural conclusion |
| Exact internal Halos commit mechanism | NOT ESTABLISHED |

This matrix is intended to prevent accidental promotion of architectural inference into source-verified fact.

---

## 14. Final Architectural Conclusion

The evidence supports a clear distinction:

**PoC boundary:**

```
SDM → SLC Software Gate → ATL/UDP → Receiver
```

Useful for demonstrating governance authority and revocation, but limited to software/transport enforcement and command acceptance.

**Production boundary:**

```
Execution Request → GIE Commit Gate → Architectural Effect
```

This is the stronger architecture because it protects the actual execution effect rather than one transport representation of the command.

### Final definition

> **GIE is a hardware-resident execution-governance boundary that prevents an unauthorized execution effect from becoming architecturally effective by enforcing governance authority at the earliest hardware-protected commit boundary.**

The central distinction is:

> **Halos answers: “Is this safe?”**
>
> **SLC answers: “Is this execution request semantically and contextually authorized?”**
>
> **GIE enforces: “Can this execution effect become system state?”**

And the critical evidence-based qualification is:

> **The accessible Halos 1.3 source establishes a validated command-acceptance/software safety-state boundary and a downstream PLC command path, but does not expose the final physical or architectural execution primitive. Therefore the GIE production boundary remains a proposed architectural boundary, not a claimed NVIDIA implementation fact.**
