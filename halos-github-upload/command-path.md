# Halos 1.3 ATL Execution Path — Detailed Source Tracing

## Overview

This document traces the exact execution path from SIPP (System Integration Point Provider) through the SLC gate insertion point to the ATL command receiver.

Each transition is documented with:
- **Source File** (from NVIDIA documented locations)
- **Function/Class**
- **Input** and **Output** specifications
- **Validation** performed at this stage
- **Container/Process Boundary** (Safety Core or external)
- **Command Emission** capability (can this stage emit the command downstream?)

---

## Execution Path Map

```
SIPP (external)
  ↓ [perception data]
SAIM / PCM (Safety Core)
  ↓ [perception assessment]
SEI (Safety Core)
  ↓ [authoritative decision]
SDM (Safety Core)
  ↓ [64-byte ATL packet]
SLC Gate ← INSERTION POINT
  ↓ [ALLOW/BLOCK decision]
ATL Command Receiver (network boundary)
  ↓ [UDP ingress]
Safety Function (Safety Core)
  ↓ [command execution]
Downstream Equipment (external)
```

---

## Stage 1: SIPP → System Input

### FACT: External Data Source

**Description:** SIPP provides raw sensor data (distance, speed, obstacles, operator input, etc.)

**Container:** External (not Safety Core)

**Input:** Sensor streams, operator controls

**Output:** Structured sensor data packet

**Validation:** None (SIPP is a data provider, not a safety validator)

**Can emit command?** No (SIPP is upstream of decision)

### Source Reference

- **Package:** `psf-oss-sources` (Debian base)
- **Location:** Not in this package (external system integration)

---

## Stage 2: SAIM / PCM (Safety Algorithm Integration Module / Perception Control Module)

### FACT: Perception Integration

**Description:** SAIM/PCM receives sensor data and applies perception algorithms. PCM performs perception control and produces perception output (e.g., object detection, trajectory prediction).

**Container:** Safety Core (protected environment)

**Input:** 
- Raw sensor data from SIPP
- Perception configuration / parameters

**Output:**
- Perception state (objects detected, trajectories, hazards)
- Confidence scores
- Timestamp

**Validation:**
- Input data sanity checks (range, type)
- Perception algorithm consistency
- Confidence threshold validation

**Can emit command?** No (SAIM/PCM produces perception data, not commands)

### Source Reference

- **Package:** `psf-desktop.deb` (access-restricted)
- **Location:** `/opt/nvidia/psf/examples/apps/metropolis/saim/` or `/opt/nvidia/psf/examples/apps/metropolis/pcm/`
- **Key Classes/Functions:** `PerceptionControlModule`, `SafetyAlgorithmIntegration`

---

## Stage 3: SEI (Safety Element Interface)

### FACT: Authoritative Decision

**Description:** SEI receives perception state from SAIM/PCM and produces an authoritative binary decision: **permissive** (operation is safe) or **restrictive** (operation is not safe).

**Container:** Safety Core (protected environment)

**Input:**
- Perception state from SAIM/PCM
- Safety policy / thresholds
- Current safe-state latch status

**Output:**
- Binary decision: `PERMISSIVE` or `RESTRICTIVE`
- Decision timestamp
- Confidence level

**Validation:**
- Perception data freshness
- Safe-state consistency
- Policy application correctness

**Can emit command?** No (SEI produces a decision, not a command packet)

### Source Reference

- **Package:** `psf-desktop.deb` (access-restricted)
- **Location:** `/opt/nvidia/psf/examples/apps/metropolis/sei/`
- **Key Classes/Functions:** `SafetyElementInterface::decide()`, `SafetyState`

---

## Stage 4: SDM (Semantic Decision Module)

### Substage 4a: Decision Reception

**Description:** SDM receives the binary decision from SEI and the current safety state.

**Input:**
- `decision: PERMISSIVE | RESTRICTIVE` (from SEI)
- `safe_state_latch: LATCHED | UNLATCHED | RELEASING`
- `sequence_counter: uint32_t` (from previous packet sequence)
- `timestamp_ms: uint64_t`

**Validation:**
- Decision freshness (timestamp within acceptable window)
- Sequence counter overflow handling

---

### Substage 4b: Opcode Selection

**Description:** SDM maps the binary decision and state into a specific ATL opcode.

**Input:**
- `decision: PERMISSIVE | RESTRICTIVE`
- `safe_state_latch`
- `sequence_counter`

**Decision Logic:**

```c
if (decision == RESTRICTIVE) {
  opcode = CMD_MUTE;  // Disable operation immediately
} else if (decision == PERMISSIVE) {
  if (safe_state_latch == LATCHED) {
    opcode = CMD_SAFE_RELEASE_REQUEST;  // Request release from latched state
  } else if (safe_state_latch == RELEASING) {
    opcode = CMD_SAFE_RELEASE_ACK;      // Acknowledge ongoing release
  } else {
    opcode = CMD_UNMUTE;                // Normal permissive command
  }
} else {
  opcode = CMD_SW_ERROR;                // Safety error
}
```

**Output:**
- Selected opcode: one of `CMD_MUTE`, `CMD_UNMUTE`, `CMD_SAFE_RELEASE_REQUEST`, `CMD_SAFE_RELEASE_ACK`, `CMD_SAFE_RELEASE_DENIED`, `CMD_SW_ERROR`

**Validation:**
- Opcode validity (enum value within valid range)

---

### Substage 4c: Packet Serialization

**Description:** SDM serializes the opcode, parameters, and integrity fields into a 64-byte ATL command packet.

**Container:** Safety Core

**Input:**
- Opcode (selected in 4b)
- Parameters (target device, duration, flags)
- Sequence counter (incremented)
- Timestamp (current system time)

**Output:**
- `packet: bytes[64]` — serialized ATL packet

**Packet Structure (FACT from NVIDIA documentation):**

| Field | Bytes | Type | Purpose |
|-------|-------|------|---------|
| Magic / Version | 0–3 | uint32 | Packet identification |
| Opcode | 4–7 | uint32 | Command type (CMD_MUTE, etc.) |
| Sequence | 8–11 | uint32 | Replay protection counter |
| Timestamp | 12–19 | uint64 | Packet generation time (ms) |
| Parameters | 20–55 | [varies] | Command-specific data |
| CRC | 56–59 | uint32 | 32-bit CRC over bytes 0–55 |
| Flags | 60–63 | uint32 | Reserved / flags |

**Validation:**
- CRC computation correctness
- Byte count exactly 64
- Opcode field within valid range
- Sequence counter increment without overflow

**Can emit command?** Not yet (packet is generated but not emitted)

### Source Reference

- **Package:** `psf-desktop.deb` (access-restricted)
- **Location:** `/opt/nvidia/psf/examples/apps/metropolis/atl/sdm/ccplex/ATLControl.cpp`
- **Key Classes/Functions:**
  - `class SDM` (or similar)
  - `void SDM::emit_command(atl_cmd_pkt_t* pkt)`
  - `atl_cmd_pkt_t SDM::serialize(opcode, params)`
- **Header:** `/opt/nvidia/psf/examples/apps/metropolis/atl/include/atl_cmd_pkt.h`

---

## Stage 5: SDM → Transport (INSERTION POINT FOR SLC GATE)

### FACT: Packet Ready for Emission

**Description:** The 64-byte packet is now ready to be sent to the ATL command receiver. This is the **narrowest point** where an SLC gate can intercept without modifying the packet.

**Container Boundary:** Safety Core → Network Boundary

**Input:**
- 64-byte ATL packet (from SDM serialization)
- Receiver address (IP:port)
- Governance state (from external SLC system)

**Validation Points (before SLC Gate):**
- Halos-internal validation (safety decision correctness)
- Packet structure correctness (CRC, byte count)

**SLC Gate Decision:**

```
def slc_decide(packet: bytes, authority: Authority, 
               governance: Governance, now_ms: int) -> (bool, str):
    # All 64 bytes are preserved on decision=True
    # Zero bytes on decision=False
    
    # Check 1: Packet size
    if len(packet) != 64:
        return (False, 'PACKET_SIZE')
    
    # Check 2: Payload binding (exact 64-byte digest)
    packet_digest = SHA256(packet)
    if packet_digest != authority.packet_sha256:
        return (False, 'PAYLOAD_BINDING')
    
    # Check 3: Target match
    if authority.target != governance.target:
        return (False, 'TARGET_MISMATCH')
    
    # Check 4: Context match
    if authority.context_id != governance.context_id:
        return (False, 'CONTEXT_MISMATCH')
    
    # Check 5: Authority expiry
    if now_ms > authority.valid_until_ms:
        return (False, 'AUTHORITY_EXPIRED')
    
    # Check 6: Epoch match (core of independent authority)
    if authority.epoch != governance.epoch:
        return (False, 'EPOCH_MISMATCH')
    
    # Check 7: Route permission
    if not governance.route_permitted:
        return (False, 'ROUTE_REVOKED')
    
    # Check 8: Safety permission
    if not governance.safety_permitted:
        return (False, 'SAFETY_DENIED')
    
    # All checks passed
    return (True, 'COMMIT_AUTHORIZED')
```

**Output:**
- **Decision:** `ALLOW` or `BLOCK`
- **Reason:** One of the check failure codes above
- **Packet bytes:** Original 64 bytes (on ALLOW) or empty (on BLOCK)

**Can emit command?** Yes — **this is the emission control point**

### SLC Gate Implementation Reference

- **Reference Code:** `~/Downloads/SLC_Halos_PoC_v0_3/slc_halos_adapter.py`
- **Key Class:** `SLCHalosAdapter`
- **Key Method:** `SLCHalosAdapter.commit(packet, authority, governance, now_ms) -> GateResult`

### Important Properties

1. **Byte Preservation:** On ALLOW, the exact 64-byte packet is forwarded unchanged
2. **Authority Binding:** Authority is bound to SHA-256(exact_64_bytes) + governance context
3. **Epoch Independence:** Epoch mismatch is the mechanism for withdrawing authority
4. **No Halos Modification:** The gate does not interpret or modify the packet

---

## Stage 6: SLC Gate → UDP Transport

### FACT: Conditional Packet Transmission

**Description:** Based on SLC gate decision, the packet is sent to the receiver or dropped.

**Container:** Network boundary

**Input:**
- Packet bytes (from SLC gate ALLOW) or empty (from SLC gate BLOCK)
- Receiver address (IP:port)

**Output:**
- UDP datagram sent (on ALLOW)
- No datagram sent (on BLOCK)

**Validation:** Transport-layer checksums (UDP checksum)

**Can emit command?** Yes — **packet reaches the network on ALLOW**

### Source Reference

- **Implementation:** UDP socket, standard BSD sockets API
- **Not in PoC:** This is standard network transport

---

## Stage 7: ATL Command Receiver Ingress (Network Boundary)

### FACT: Packet Reception

**Description:** The ATL command receiver is a UDP socket listener. It receives the packet (if SLC gate allowed it) on a configured port.

**Container:** Safety Core (receiver logic)

**Input:**
- UDP datagram containing 64-byte ATL packet (if available)
- Receiver socket parameters (port, timeout)

**Output:**
- Received packet bytes (on success)
- Error/timeout (if no packet within timeout window)

**Validation:**
- UDP port binding success
- Datagram size exactly 64 bytes
- Socket timeout handling

**Can emit command?** Not yet (receiver just ingested the packet)

### Source Reference

- **Package:** `psf-desktop.deb` (access-restricted)
- **Location:** `/opt/nvidia/psf/examples/apps/metropolis/atl/udp_cmd_receiver/cmd_rx.cpp`
- **Key Classes/Functions:**
  - `class CommandReceiver` (or similar)
  - `void CommandReceiver::listen(port)`
  - `atl_cmd_pkt_t* CommandReceiver::receive_packet(timeout_ms)`

---

## Stage 8: ATL Command Receiver Validation

### FACT: Halos-Level Packet Validation

**Description:** The receiver validates the packet using Halos's own integrity and freshness mechanisms. This is **independent** of SLC gate validation.

**Container:** Safety Core (receiver logic)

**Input:**
- 64-byte packet from UDP socket
- Previous packet state (last sequence, last timestamp)
- Safe-state latch status

**Output:**
- Valid/Invalid decision
- Parsed opcode (if valid)

**Validation Checks (Halos-level, independent of SLC):**

1. **CRC Validation:**
   - Compute CRC over bytes 0–55
   - Compare with CRC in bytes 56–59
   - Reject if mismatch

2. **Sequence Validation:**
   - Extract sequence counter from bytes 8–11
   - Check counter > previous_sequence (or wrapped correctly)
   - Reject if sequence invalid (replay, out-of-order)

3. **Timestamp Freshness:**
   - Extract timestamp from bytes 12–19
   - Check timestamp is recent (within acceptable window)
   - Reject if stale (>1000ms old, for example)

4. **Heartbeat Validation:**
   - Verify periodic keep-alive signals
   - Reject if heartbeat lost (e.g., >500ms since last valid packet)

5. **Safe-State Latch:**
   - If latch is LATCHED, only accept SAFE_RELEASE_REQUEST or SAFE_RELEASE_ACK
   - Reject incompatible opcodes while latched

**Can emit command?** Not yet (packet is validated but not interpreted)

### Source Reference

- **Package:** `psf-desktop.deb` (access-restricted)
- **Location:** `/opt/nvidia/psf/examples/apps/metropolis/atl/udp_cmd_receiver/cmd_rx.cpp`
- **Key Functions:**
  - `bool CommandReceiver::validate_crc(packet)`
  - `bool CommandReceiver::validate_sequence(packet)`
  - `bool CommandReceiver::validate_freshness(packet)`
  - `bool CommandReceiver::validate_heartbeat(packet)`
  - `bool CommandReceiver::validate_safe_state(packet, current_latch)`

---

## Stage 9: Command Interpretation & Parsing

### FACT: Opcode Extraction

**Description:** The validated packet is deserialized. The opcode is extracted from bytes 4–7.

**Container:** Safety Core

**Input:**
- Validated 64-byte packet

**Output:**
- Opcode: one of `CMD_MUTE`, `CMD_UNMUTE`, `CMD_SAFE_RELEASE_REQUEST`, `CMD_SAFE_RELEASE_ACK`, `CMD_SAFE_RELEASE_DENIED`, `CMD_SW_ERROR`
- Parameters (extracted from bytes 20–55)

**Validation:**
- Opcode enum value within valid range
- Parameters interpreted correctly for the opcode type

**Can emit command?** Not yet (interpreted but not executed)

### Source Reference

- **Package:** `psf-desktop.deb` (access-restricted)
- **Location:** `/opt/nvidia/psf/examples/apps/metropolis/atl/udp_cmd_receiver/cmd_rx.cpp`
- **Key Functions:**
  - `void CommandReceiver::parse_packet(packet) -> opcode, params`
  - `void CommandReceiver::dispatch_opcode(opcode, params)`

---

## Stage 10: Safety Function Dispatch

### FACT: Command Execution

**Description:** The receiver dispatches the interpreted opcode to the corresponding safety function.

**Container:** Safety Core (safety-critical state machine)

**Input:**
- Opcode: `CMD_MUTE`, `CMD_UNMUTE`, `CMD_SAFE_RELEASE_REQUEST`, etc.
- Parameters: Target device, duration, flags

**Output:**
- State transition (safety state machine)
- Actuator command (e.g., motor disable, brake engage)

**Dispatch Logic:**

```c
switch (opcode) {
  case CMD_MUTE:
    safety_state_machine.set_muted();
    actuator.disable_operation();
    break;
  
  case CMD_UNMUTE:
    safety_state_machine.set_unmuted();
    actuator.enable_operation();
    break;
  
  case CMD_SAFE_RELEASE_REQUEST:
    safety_state_machine.request_release();
    break;
  
  case CMD_SAFE_RELEASE_ACK:
    safety_state_machine.acknowledge_release();
    break;
  
  case CMD_SAFE_RELEASE_DENIED:
    safety_state_machine.deny_release();
    break;
  
  case CMD_SW_ERROR:
    safety_state_machine.signal_error();
    actuator.safe_shutdown();
    break;
}
```

**Validation:**
- State transition validity (can only transition from certain states)
- Actuator availability (motor is responsive, brake is functional)
- Redundancy checks (if applicable)

**Can emit command?** Yes — **this is the actual safety-critical execution boundary**

### Source Reference

- **Package:** `psf-desktop.deb` (access-restricted)
- **Location:** `/opt/nvidia/psf/examples/apps/metropolis/atl/sdm/` or safety function handler
- **Key Classes/Functions:**
  - `class SafetyStateMachine`
  - `void SafetyStateMachine::on_cmd_mute()`
  - `void SafetyStateMachine::on_cmd_unmute()`
  - `void SafetyStateMachine::on_safe_release_request()`

---

## Stage 11: Downstream Equipment

### FACT: Physical Safety Action

**Description:** The safety function controls downstream equipment (motors, brakes, release mechanisms, etc.).

**Container:** External (not Safety Core)

**Input:**
- Command from safety state machine (e.g., "motor disable", "brake engage")

**Output:**
- Physical state change (motor stops, brake applies, gate latches)

**Validation:** Hardware sensors (motor speed feedback, brake pressure, gate position)

**Can emit command?** No — equipment state is the outcome, not an emitted command

---

## Summary Table

| Stage | Component | Input | Output | Validation | SLC? | Emit? |
|-------|-----------|-------|--------|-----------|------|-------|
| 1 | SIPP | Sensors | Sensor data | None | No | No |
| 2 | SAIM/PCM | Sensor data | Perception state | Perception sanity | No | No |
| 3 | SEI | Perception | Binary decision | Decision freshness | No | No |
| 4a–4c | SDM | Decision | 64-byte packet | CRC, structure | No | No |
| **5** | **SLC Gate** | **Packet** | **ALLOW/BLOCK** | **Authority, epoch, context** | **YES** | **YES** |
| 6 | UDP Transport | Packet/empty | UDP datagram | UDP checksum | No | Yes |
| 7 | Rx Ingress | Datagram | Received bytes | Socket sanity | No | No |
| 8 | Rx Validation | Packet | Valid/Invalid | CRC, sequence, freshness, heartbeat, latch | No | No |
| 9 | Parse | Valid packet | Opcode, params | Enum validity | No | No |
| 10 | Dispatch | Opcode | State transition | State validity | No | Yes |
| 11 | Equipment | Command | Physical state | Hardware sensors | No | No |

---

## Critical Distinction: SLC vs. Halos Validation

| Aspect | Halos (Stages 1–4, 8–11) | SLC (Stage 5) |
|--------|--------------------------|---|
| **Validates** | Is this command safe to execute? | Does this command have current execution authority? |
| **Input** | Perception, safety policy, packet structure | Exact packet digest, governance state, execution epoch |
| **Decision** | Safety (permissive/restrictive) | Authority (allowed/denied) |
| **Failure Mode** | Restrictive command (e.g., CMD_MUTE) | Packet dropped (not sent to receiver) |
| **Independent?** | No — Halos is a safety module | **Yes** — SLC is independent governance layer |
| **Can be bypassed by** | Compromise of Halos logic | Compromise of SLC authority database or governance state |

---

## Decisive Experiment Flow

### Setup
- Packet = valid CMD_UNMUTE (from SDM)
- Authority epoch = 481
- Governance epoch = 481
- Result: SLC allows packet to receiver

### Trigger
- Governance epoch advances to 482 (authority revoked)

### Test
- Exact same packet bytes replayed
- Halos safety logic: still permissive (would emit same packet again)
- Packet integrity: unchanged (CRC still valid)
- SLC decision: EPOCH_MISMATCH → BLOCK
- Receiver: zero packets received

### Evidence
- Halos: "I still think this is safe"
- SLC: "But you don't have authority to execute it"
- Result: Command stopped by SLC, not by Halos

This proves **independent execution-authority enforcement** at Stage 5.

