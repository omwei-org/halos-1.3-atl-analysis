# COMMIT_BOUNDARY_ANALYSIS.md — Summary

## Key Finding

**The natural GIE Commit Gate location is at the architectural state transition boundary (Candidate D):**

```
Safety Function (Halos)
         ↓
    State Write Request
         ↓
    ╔═══════════════════╗
    ║  GIE Gate (HW)    ║
    ║  Check:           ║
    ║  • Epoch match    ║
    ║  • Authority OK   ║
    ║  • Context OK     ║
    ╚═══════════════════╝
         ↓
    COMMIT / BLOCK
         ↓
    State Register
```

---

## Six Candidate Boundaries Evaluated

| # | Candidate | Location | Verdict | Reason |
|---|-----------|----------|---------|--------|
| A | Pre-SEI | Before safety decision | ❌ REJECT | Gate re-implements SEI; needs new processor |
| B | SDM→ATL | Packet transmission (current PoC) | ✓ GOOD PoC | Proves concept; but premature for hardware |
| C | Receiver→Execute | Before command dispatch | ✓ BETTER | Closer to effect; but not at commit point |
| D | Architectural Commit | State write boundary | ✓✓✓ OPTIMAL | All info available; hardware-natural; bypass-resistant |
| E | Actuation | Physical output | ❌ REJECT | Too late; state already committed |

---

## Why Candidate D Wins

### 1. Information Availability
At state write, all necessary context is present:
- Source state (current)
- Destination state (requested)
- Governance epoch
- Authority record
- Command semantics

### 2. Bypass Resistance
If attacker compromises software above D:
- ❌ Cannot force state write (hardware gate enforces)
- ❌ Cannot bypass authority check
- ❌ Can request transition, but cannot make it effective

### 3. No Halos Modification
- Halos SEI/SDM logic is untouched
- Safety decision remains authoritative
- Gate is orthogonal enforcement layer

### 4. Atomic Transitions
- Either full state transition commits (with valid authority)
- Or no state change occurs
- No partial states possible

### 5. Hardware Feasible
- Integrates into SoC state machine logic
- No separate processor needed
- Straightforward: observe write request → check authority → allow/block

---

## Three Distinct Concepts

### Safety Decision (Halos)
> Is this action safe?
- Owner: SEI
- Decides: PERMISSIVE or RESTRICTIVE
- Gate location: SEI itself

### Authority Decision (Equinibrium)
> Is this action authorized?
- Owner: GIE gate
- Decides: AUTHORIZED or REVOKED
- Gate location: Commit boundary (D)

### Result
```
Halos: PERMISSIVE + Equinibrium: AUTHORIZED → Transition commits
Halos: PERMISSIVE + Equinibrium: REVOKED   → Transition blocked at gate
Halos: RESTRICTIVE + Equinibrium: ANY     → Never reaches gate (SEI blocks)
```

Both gates must pass. Orthogonal enforcement.

---

## Current PoC vs. Hardware Implementation

### PoC (Candidate B: SDM→ATL)
```
Proves:
✓ Authority gating mechanism works
✓ Governance revocation blocks packet
✓ Halos remains independent

Does NOT prove:
❌ Already-admitted command cannot transition to unauthorized state
❌ Hardware gate at D is necessary
❌ Full protection against software compromise
```

### Hardware Gate (Candidate D)
```
Proves everything PoC proves, PLUS:
✓ Even accepted command cannot become effective if authority revoked
✓ State write is prevented at hardware level
✓ Software compromise is insufficient to bypass gate
✓ Atomic transitions with authority verification
```

**Relationship:** PoC validates the **concept**. Hardware gate validates the **implementation**.

---

## Trusted Computing Boundary

### Above Gate (Software, not protected):
- Perception input
- SAIM/PCM fusion
- SEI safety logic
- SDM command generation
- ATL packet transport
- Receiver parsing
- Safety function pre-commit logic

**Trust model:** Determines WHAT to transition and WHETHER it's safe.

### At Gate (Hardware, protected):
- Authority check (epoch match)
- Context validation
- TTL verification
- Governance flags

**Trust model:** Determines WHETHER to actually commit.

### Below Gate (Hardware, effected):
- State register write
- Actuation drivers
- Physical output

**Protection:** Gate prevents unauthorized write → no unauthorized state → no unauthorized actuation.

---

## Three Experiments (Proof)

### Experiment 1: Authority Revocation at Gate
```
T0: Valid command, authority OK → Motor disables ✓
T1: Governance epoch advances (revokes authority)
T1+: Same command replayed
    • Halos: still permissive (unchanged safety logic)
    • Packet: still valid (CRC, sequence OK)
    • GIE gate: EPOCH_MISMATCH → BLOCK ✓
    • Result: Motor stays disabled (old state unchanged)

Proves: Gate at D is the right location (after receiver accepts but before state commits)
```

### Experiment 2: Atomic State Commit
```
Transition request: LATCHED → RELEASING (3 internal operations)
- With GIE gate: Gate observes complete destination state
  • Either all 3 operations commit atomically (with valid authority)
  • Or none commit (authority invalid)
  • No partial states

Proves: D ensures atomicity + authority verification
```

### Experiment 3: Authority ≠ Safety
```
Scenario A - Safety block:
    SEI: RESTRICTIVE → SDM: CMD_MUTE → Motor disabled
    Reason: Safety decision

Scenario B - Authority block:
    SEI: PERMISSIVE → SDM: CMD_UNMUTE
    GIE gate: EPOCH_MISMATCH → BLOCK
    Motor stays disabled
    Reason: Authority, not safety

Proves: A and B are orthogonal; GIE gate is independent enforcement
```

---

## Final Architecture

```
Halos (Safety)                Equinibrium (Authority)
├─ SIPP (perception)
├─ SAIM/PCM (fusion)
├─ SEI (safety decision)
├─ SDM (command gen)
├─ ATL (transport)
├─ Receiver (parse)
├─ Safety Function
│    ↓
│ [Request state transition]
│    ↓
│ ╔═══════════════════════╗
│ ║ GIE COMMIT GATE (HW)  ║ ← Equinibrium enforcement
│ ║                       ║
│ ║ Check epoch match     ║
│ ║ Check authority TTL   ║
│ ║ Check governance      ║
│ ║ Check context         ║
│ ║                       ║
│ ║ COMMIT / BLOCK        ║
│ ╚═══════════════════════╝
│    ↓
├─ State register (architectural)
├─ Actuation drivers
└─ Physical output
```

**Properties:**
1. Halos is untouched (still owns safety decision)
2. Equinibrium gate is independent (owns authority decision)
3. Both gates must pass for state transition to execute
4. Gate location is at maximum protection point (state write)
5. No new processor needed
6. Hardware-implementable (SoC state machine control logic)

---

## Conclusion

The **GIE Commit Gate should sit at the architectural state transition boundary**, specifically where Safety Function requests a state machine state register write and before that write becomes observable.

This location provides:
- ✓ Complete protection against unauthorized state transitions
- ✓ Independence from Halos safety logic
- ✓ Bypass resistance against software compromise
- ✓ Atomic, verified state commits
- ✓ Hardware feasibility without new processor
- ✓ Alignment with Equinibrium SIF architecture

The current software PoC (Candidate B) validates the concept and will guide early integration. The hardware gate (Candidate D) provides the production implementation.

