# Source Evidence Update — NVIDIA Halos 1.3 ATL Command Receiver

**Date:** 2026-09-08  
**Project:** Equinibrium / OMWEI  
**Purpose:** Update the Halos 1.3 execution-boundary analysis with direct evidence from the NVIDIA `psf-desktop-dev` reference source package.

---

## 1. Evidence Status

This update incorporates direct inspection of the NVIDIA Halos 1.3 development package, specifically:

- `atl/udp_cmd_receiver/cmd_rx.cpp`
- `atl/include/atl_cmd_pkt.h`
- `atl/sdm/ccplex/ATLControl.cpp`
- `atl/sdm/ccplex/ATLControl.h`
- `atl/sdm/ccplex/ATL.cpp`

The evidence changes the confidence level of the command-path reconstruction, but **does not expose the downstream physical actuator / PLC implementation** in the shipped examples.

---

## 2. Confirmed Halos Command Path

```text
SDM / ATLControl
      |
      | MUTE / UNMUTE / error / release command
      v
64-byte ATL CmdPacket
      |
      | UDP
      v
ATL UDP Command Receiver (`cmd_rx.cpp`)
      |
      +--> packet validation
      +--> command interpretation
      +--> software safe-state / release handling
      +--> ACK
      +--> optional VST relay
      |
      v
[downstream PLC / controller / execution implementation]
      |
      v
architectural / physical effect
```

The final downstream implementation is not present in the inspected example source and must therefore not be presented as verified NVIDIA implementation detail.

---

## 3. `atl_cmd_pkt.h`: Command Semantics

The reference header defines a 64-byte packed command packet and explicitly defines:

```text
CMD_MUTE   0x02  /* Allow Operation */
CMD_UNMUTE 0x07  /* Prevent Operation */
```

It also defines hardware/software error and safe-release commands.

The packet contains an identifier, sequence number, command, timestamps, CRC32, and two object records.

CRC32 establishes packet integrity; it does not establish execution authority. Dynamic sequence/timestamp fields also mean that an exact digest of the complete packet would identify a packet instance rather than provide a stable production authority anchor.

---

## 4. `ATLControl.cpp`: SDM Decision to PLC Command Path

Direct source inspection confirms that `ATLControl.cpp` constructs a `CmdPacket`, populates the command, sequence and timestamp, calculates CRC32, and sends the complete packet using `sendto()` to a configured PLC destination.

The source explicitly describes this as:

```text
PLC command socket (send to PLC, receive ACKs)
```

The PLC destination is configured through `plcIP` / `plcPort`. Decision logic explicitly emits MUTE, UNMUTE and fail-safe commands. Safe-state latching and PLC-authoritative safe-release handling are implemented in the SDM/ATL control software.

**Conclusion:** the SDM→PLC command path is source-backed, but the actual PLC-side actuator/control implementation is not exposed by the inspected examples.

---

## 5. `cmd_rx.cpp`: What the Receiver Actually Does

The receiver performs:

1. exact packet-size validation;
2. expected-sender validation;
3. packet identifier validation;
4. CRC32 validation;
5. command whitelist validation;
6. heartbeat handling;
7. software safe-state / release-state handling;
8. ACK construction and transmission;
9. optional VST relay.

It runs an ordinary UDP socket event loop and calls `handleReceive()` for accepted datagrams.

The source maintains software state such as `safe_release_prompt_ready_` and `console_latched_`. Safe release is exposed through stdin/FIFO and a startup release loop.

The receiver is therefore best characterized as a:

> **validated command acceptance and software safety-state management boundary**

It should **not** be characterized as the verified physical execution boundary.

---

## 6. What `cmd_rx.cpp` Does NOT Show

The inspected receiver source does not contain evidence of:

- GPIO writes;
- actuator or motor control;
- `ioctl()`-based actuator control;
- direct hardware register writes;
- a PLC driver implementation;
- a physical output write;
- or another exposed downstream architectural commit primitive.

The broader source search across the supplied ATL and Proximity examples likewise did not identify such an implementation.

This is an **evidence limitation**, not evidence that no such implementation exists in the complete NVIDIA product.

---

## 7. Consequence for the GIE Boundary

The evidence supports three distinct boundaries:

### A. Safety decision boundary
Halos / SEI / SDM determine whether the requested action is permitted from the safety perspective.

### B. Command acceptance boundary
The ATL receiver validates and accepts the command representation and manages software safety/release state.

### C. Architectural execution boundary
The protected point where the requested execution effect becomes system state.

**B is a valid software PoC boundary but not the production GIE boundary.**

The production GIE boundary remains:

> **the earliest hardware-protected point at which the requested execution effect becomes architecturally effective.**

This point is architecture-dependent and is not exposed by the inspected Halos examples.

---

## 8. Revised PoC / Production Model

### Software PoC

```text
SDM
  |
  v
SLC Software Gate
  |
  v
ATL / UDP
  |
  v
cmd_rx
```

This can demonstrate governance authority, revocation, stale-context rejection, and command admission control.

### Production GIE

```text
Execution Request
      |
      v
Execution Logic
      |
      v
GIE Commit Gate
      |
      +---- BLOCK --> no protected architectural effect
      |
      +---- ALLOW --> architectural effect
```

The production gate protects the **execution effect**, not merely the packet carrying the request.

---

## 9. Safe-Release Finding

The receiver source provides an important distinction:

```text
software safe-state latch
        !=
hardware execution authority
```

A receiver can clear or maintain software latch state, accept a safe-release command, and report that normal operation has resumed. That does not by itself establish that an unauthorized execution effect is impossible downstream.

For GIE, safe release therefore becomes authoritative only when the corresponding protected governance state is reflected at the hardware commit boundary.

---

## 10. Refined Architectural Invariant

The Halos evidence supports the following stronger formulation:

> **A valid Halos command, a valid UDP packet, or an accepted receiver state must not by itself be sufficient to make a protected execution effect architecturally effective.**

The production invariant is:

> **No software component outside the trusted governance/commit boundary can unilaterally force a protected execution effect to become architecturally effective.**

This is the property that distinguishes GIE from packet validation, command filtering, and software safety-state handling.

---

## 11. Revised Boundary Classification

| Boundary | Evidence | GIE role |
|---|---|---|
| Pre-SEI | Halos architecture | Too early |
| SEI / SDM | Safety decision / command generation | Safety, not final authority |
| SDM → ATL / UDP | Source-verified | **Software PoC** |
| ATL UDP receiver | Source-verified | Command acceptance / software state |
| Receiver → downstream execution | Not exposed | Candidate integration zone |
| Earliest hardware architectural commit | Not exposed; architectural requirement | **Production GIE target** |
| Physical actuation | Not exposed | Secondary interlock only, where appropriate |

---

## 12. Evidence Discipline Going Forward

Do not state that `cmd_rx.cpp` directly controls the physical actuator unless additional source evidence is obtained.

Do not state that the UDP receiver is the final execution boundary.

Do state that:

1. NVIDIA exposes a source-backed SDM→PLC command protocol;
2. the ATL receiver validates and accepts the command;
3. the receiver maintains software safety/release state;
4. the supplied examples do not expose the downstream actuator/PLC implementation;
5. therefore the production GIE boundary must be defined architecturally rather than inferred from the UDP receiver;
6. the UDP path remains an excellent software PoC boundary.

---

## 13. Final Updated Conclusion

The new source evidence does **not** weaken the GIE architecture. It makes the argument more precise.

NVIDIA Halos demonstrates a clear chain from safety decision to command generation and command acceptance. The supplied source does not expose the final physical execution implementation. Therefore the strongest vendor-independent enforcement point is not the packet and not the receiver, but the earliest hardware-protected architectural commit point downstream of them.

```text
Halos
  = safety judgment

SDM / ATL
  = execution request generation

cmd_rx / PLC protocol
  = command acceptance and software state handling

GIE
  = hardware-enforced execution authority at architectural commit
```

### Final principle

> **Halos answers whether an action is safe. SLC determines whether the execution request is semantically and contextually authorized. GIE enforces whether the resulting execution effect may become system state.**
