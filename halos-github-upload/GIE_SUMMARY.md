# GIE_ARCHITECTURE_DEFINITION.md — Executive Summary

## What Is GIE?

**Governance and Integrity Enforcement (GIE) Commit Gate** is a hardware-resident architectural boundary that prevents unauthorized execution effects from becoming system state.

---

## Core Concept

### Three Layers

```
Layer 1: HALOS (Safety)
├─ Perception → Decision → Command
└─ Question: "Is this safe?"

Layer 2: GIE (Authority)
├─ Commit Request → Authority Check → State Write
└─ Question: "Is this authorized?"

Layer 3: ARCHITECTURE
├─ State Register → Actuation
└─ Result: Physical effect (or prevention thereof)
```

### Both Gates Must Pass

```
Halos: PERMISSIVE + GIE: AUTHORIZED → State commits
Halos: PERMISSIVE + GIE: UNAUTHORIZED → State blocked by GIE
Halos: RESTRICTIVE + GIE: ANY → Never reaches GIE (blocked by Halos)
```

---

## The Protected Object: Commit Request

**NOT:** A packet or command (those are transport-level)

**IS:** A hardware event that signals "I am about to transition from state S to state S', and I am requesting permission"

```
CommitRequest {
    source_state: Current architectural state
    destination_state: Requested new state
    semantic_id: Unique ID of the command/action
    execution_id: Who is executing this (context ID)
    governance_epoch: Current governance generation
    authority_context: Governance context identifier
}
```

---

## GIE Decision Function

### Input

```
CommitRequest
+
HardwareGovernanceState {
    current_epoch
    allowed_contexts
    revocation_bitmap
    safe_state_register
    emergency_mode
}
```

### Decision Logic

```
AUTHORIZED(cr) :=
    (cr.epoch == hw.current_epoch)
    AND (cr.context IN hw.allowed_contexts)
    AND (cr.semantic_id NOT IN hw.revocation_bitmap)
    AND (cr.execution_id matches original execution)
    AND (NOT hw.emergency_mode)
    AND (state transition is consistent)
```

### Output

```
COMMIT → state register written, state becomes observable
BLOCK → state register unchanged, exception raised
EXCEPTION → emergency: write safe_state, lock governance
```

---

## Hardware Trust Boundary

### Inside GIE (Protected)

```
HARDWARE-RESIDENT:
✓ current_epoch (immutable by software)
✓ allowed_contexts (write-protected)
✓ revocation_bitmap (write-protected)
✓ safe_state_register
✓ emergency_mode flag
✓ atomicity lock
```

### Outside GIE (Not Protected)

```
SOFTWARE-SUPPLIED:
✗ Perception data
✗ Safety decision (SEI/SDM)
✗ Command parsing
✗ Execution logic
    (but validated by GIE at commit)
```

**Both assumed to be protected by other mechanisms (Halos, runtime, etc.)**

---

## Key Properties

### 1. Epoch-Based Authority

Governance maintains a **monotonic epoch counter**:
- Increment = revoke all previous authorizations
- Old epoch < current epoch → automatic BLOCK
- No cryptography needed (simpler than hash binding)

### 2. Atomicity (TOCTOU Prevention)

```
decision = evaluate(commit_request)
if decision == ALLOW:
    acquire_lock()
    if current_epoch still matches:
        write_state()
    else:
        BLOCK  (governance changed mid-evaluation)
    release_lock()
```

### 3. Bypass Resistance

| Attack | Protection |
|--------|-----------|
| Modify command | semantic_id binding |
| Hijack context | execution_id match |
| Replay old epoch | monotonic epoch check |
| Direct write state | hardware write protection |
| Compromise receiver | GIE gate is downstream |
| Compromise SDM | GIE gate is independent |
| TOCTOU race | atomic snapshot + lock |

### 4. Minimal Hardware

- ~500 lines HDL
- ~5K-10K gates @ 28nm
- ~0.1-0.5 mm² (rough estimate)
- Integrates into existing SoC state machine

---

## GIE vs. Halos vs. Packet-Level PoC

### Halos (Safety Decision)

```
SEI: "Is this safe?" → PERMISSIVE or RESTRICTIVE
SDM: Generate command
```

### Packet-Level PoC (SDM → ATL)

```
SLC: "Does this packet have authority?" → ALLOW or BLOCK
Prevents unauthorized packet from reaching receiver
```

**Limitation:** Receiver could be compromised and issue direct state write

### GIE (Authority at Commit)

```
GIE: "Does this execution context have authority 
      to commit this specific state transition 
      in the current governance epoch?" → COMMIT or BLOCK
      
Prevents unauthorized state transition even after receiver
```

**Improvement:** Catches attempts to bypass receiver

---

## Three Experiments to Prove GIE Works

### Experiment 1: Epoch Revocation Blocks Commit

```
t0: Authority valid (epoch 481) → state commits ✓
t1: Governance revokes (epoch 482)
t2: Same command replayed → GIE checks epoch 481 vs 482 → BLOCK ✓
    Motor state unchanged despite valid Halos decision
```

### Experiment 2: Compromised Receiver Caught

```
Attacker compromises receiver, issues arbitrary state transition
    ↓
GIE checks authorization
    ↓
If epoch is stale or semantic_id is revoked: BLOCK ✓
```

### Experiment 3: Authority ≠ Safety

```
Scenario A: Safety blocks (SEI rejects as unsafe)
    → Never reaches GIE
    
Scenario B: Safety permits but authority blocks (GIE rejects)
    → Safety logs show "permissive"
    → GIE logs show "unauthorized"
    → Motor state unchanged
    → Proves orthogonal enforcement
```

---

## Hardware Implementation Paths

### RISC-V

```
Custom instruction + exception handler
GIE evaluation logic responds to exception
Decision routed back to instruction handler
```

### Arm

```
TrustZone monitor or system control coprocessor
Observes state write requests via system interconnect
GIE decision gates write permission
```

### Accelerator / Safety Controller

```
Command enters accelerator FSM
GIE sidecar monitors FSM transitions
Blocks or allows state write in accelerator datapath
```

**Common primitive:** Write interception + decision gate

---

## PoC vs. Production

### PoC (SDM → ATL software gate)

- ✓ Validates authority concept works
- ✓ Useful for early testing
- ✗ Bypassable if receiver compromised

### Production (GIE hardware gate)

- ✓ Validates authority enforcement at hardware level
- ✓ Complete protection against software compromise
- ✓ Bypass-resistant (hardware enforces)

**Relationship:** PoC proves concept. Production implements enforcement at the architectural point where it matters (state commit).

---

## The Final Answer

**What must happen in hardware between an execution request and an architectural state transition?**

1. Authority validation (epoch, context, revocation checks)
2. Governance state verification (immutable hardware state)
3. Atomicity enforcement (snapshot + lock prevents TOCTOU)
4. Write interception (block state write if unauthorized)
5. Exception signaling (communicate decision to software)
6. Audit logging (record block events)
7. Emergency handling (force safe state if needed)

**This is GIE.**

It is the minimal hardware mechanism that prevents unauthorized execution from becoming system state while remaining independent of the safety decision layer (Halos or equivalent).

---

## Next Document

This definition is the architectural baseline for:

- Hardware microarchitecture / block-level specification
- RTL implementation
- Integration with NVIDIA Halos 1.3 (and other safety systems)
- Formal verification / safety analysis

