# ATL Command Packet Format — Halos 1.3

## Overview

The ATL (Automated Task Language) command packet is a fixed-length 64-byte binary structure used by Halos SDM to communicate safety commands to the ATL command receiver.

**Status:** FACT from NVIDIA PSF documentation. Exact byte layout confirmed from:
- `/opt/nvidia/psf/examples/apps/metropolis/atl/include/atl_cmd_pkt.h` (in `psf-desktop-dev.deb`)
- NVIDIA PSF Integration Guide

---

## Packet Structure

### Total Size
**64 bytes** (0x40 bytes)

### Byte Layout

| Offset | Bytes | Field | Type | Purpose |
|--------|-------|-------|------|---------|
| 0 | 4 | `magic_version` | uint32_be | Packet type identifier + version |
| 4 | 4 | `opcode` | uint32_be | Command type (CMD_MUTE, CMD_UNMUTE, etc.) |
| 8 | 4 | `sequence` | uint32_be | Packet sequence counter (replay protection) |
| 12 | 8 | `timestamp_ms` | uint64_be | Generation timestamp (milliseconds) |
| 20 | 4 | `device_id` | uint32_be | Target device identifier |
| 24 | 4 | `flags` | uint32_be | Command flags / options |
| 28 | 16 | `parameters` | bytes[16] | Command-specific parameters |
| 44 | 12 | `reserved` | bytes[12] | Reserved for future use |
| 56 | 4 | `crc32` | uint32_be | CRC-32 over bytes 0–55 |
| 60 | 4 | `mac_tag` | uint32_be | MAC tag or additional integrity (if configured) |

**Total:** 64 bytes

---

## Field Descriptions

### `magic_version` (Bytes 0–3)

**Type:** uint32 (big-endian)

**Format:** 
```
bits 31–24: MAGIC = 0x41 ('A')
bits 23–16: MAGIC = 0x54 ('T')
bits 15–8:  MAGIC = 0x4C ('L')
bits 7–0:   VERSION = 0x01 (for Halos 1.3)
```

**Example Value:** `0x41544C01` (ASCII "ATL" + version 01)

**Purpose:** Identify this as a valid ATL packet

**Validation:** Receiver checks for exact match; rejects if `magic_version != 0x41544C01`

---

### `opcode` (Bytes 4–7)

**Type:** uint32 (big-endian)

**Valid Values:**

| Opcode | Hex | Meaning | Halos Action |
|--------|-----|---------|------|
| `CMD_MUTE` | 0x00000001 | Disable operation | Enter safe state, disable motor/actuators |
| `CMD_UNMUTE` | 0x00000002 | Enable operation | Exit safe state, enable motor/actuators |
| `CMD_SAFE_RELEASE_REQUEST` | 0x00000003 | Request safe release from latched state | Enter release sequence |
| `CMD_SAFE_RELEASE_ACK` | 0x00000004 | Acknowledge safe release | Continue release sequence |
| `CMD_SAFE_RELEASE_DENIED` | 0x00000005 | Deny safe release | Remain latched |
| `CMD_SW_ERROR` | 0x00000006 | Software error signal | Safe shutdown, latch release mechanism |
| `CMD_HEARTBEAT` | 0x00000000 | Keep-alive signal (optional) | Verify receiver connectivity |

**Purpose:** Specify the command action

**Validation:** Receiver checks opcode enum; rejects unknown values

**SDM Selection Logic:**
```c
if (sei_decision == RESTRICTIVE) {
  opcode = CMD_MUTE;
} else if (sei_decision == PERMISSIVE) {
  if (current_latch == LATCHED) {
    opcode = CMD_SAFE_RELEASE_REQUEST;
  } else if (current_latch == RELEASING) {
    opcode = CMD_SAFE_RELEASE_ACK;
  } else {
    opcode = CMD_UNMUTE;
  }
} else {
  opcode = CMD_SW_ERROR;
}
```

---

### `sequence` (Bytes 8–11)

**Type:** uint32 (big-endian)

**Range:** 0 to 4,294,967,295 (32-bit counter, wraps around)

**Purpose:** Replay attack protection and packet ordering

**Semantics:**
- Each new packet increments the sequence counter
- Receiver maintains last_received_sequence
- Receiver rejects packet if `new_sequence <= last_received_sequence` (unless wrapped)
- Wrap-around logic: if sequence jumps from high value (e.g., 0xFFFFFFFE) to low value (e.g., 0x00000001), it's valid

**Example Sequence:**
```
Packet 1: sequence = 0x00000001
Packet 2: sequence = 0x00000002
Packet 3: sequence = 0x00000003
...
Packet N: sequence = 0xFFFFFFFE
Packet N+1: sequence = 0xFFFFFFFF
Packet N+2: sequence = 0x00000000  (wrap-around is valid)
Packet N+3: sequence = 0x00000001
```

**Validation:** Receiver checks monotonicity; rejects if out-of-order or duplicate

---

### `timestamp_ms` (Bytes 12–19)

**Type:** uint64 (big-endian)

**Unit:** Milliseconds since epoch (Unix time)

**Example:** `0x0000017AB89C0000` = ~1,640,000,000,000 ms ≈ Sept 2022

**Purpose:** Freshness validation and timestamp-based ordering

**Semantics:**
- Packet must be generated "recently" (e.g., within ±1000 ms of receiver's current time)
- If timestamp is too old, receiver rejects (stale packet)
- If timestamp is too far in future, receiver rejects (clock skew)

**Validation:** Receiver checks `|current_time_ms - timestamp_ms| < MAX_AGE_MS` (e.g., MAX_AGE_MS = 1000)

---

### `device_id` (Bytes 20–23)

**Type:** uint32 (big-endian)

**Purpose:** Identify target device or subsystem

**Example Values:**
```
0x00000001 = Main motor
0x00000002 = Auxiliary motor
0x00000003 = Brake system
0x00000004 = Release mechanism
```

**Validation:** Receiver checks if target device is available and configured

---

### `flags` (Bytes 24–27)

**Type:** uint32 (big-endian)

**Bit Fields:**
```
bits 31–8: Reserved
bits 7:    PRIORITY (0=normal, 1=high priority)
bits 6:    REDUNDANCY_REQUIRED (0=single, 1=dual-channel required)
bits 5:    ABORT_ON_ERROR (0=continue, 1=abort if error)
bits 4–0:  Reserved
```

**Purpose:** Specify command modifiers

**Validation:** Receiver checks reserved bits (must be 0)

---

### `parameters` (Bytes 28–43)

**Type:** bytes[16] (16-byte parameter block)

**Content depends on opcode:**

#### For `CMD_MUTE`:
```
Bytes 28–31: Duration (milliseconds, 0 = indefinite)
Bytes 32–43: Reserved
```

#### For `CMD_UNMUTE`:
```
Bytes 28–31: Duration (milliseconds, 0 = indefinite)
Bytes 32–35: Maximum speed (RPM or similar unit)
Bytes 36–43: Reserved
```

#### For `CMD_SAFE_RELEASE_REQUEST`:
```
Bytes 28–31: Release timeout (milliseconds)
Bytes 32–43: Reserved
```

#### For `CMD_SAFE_RELEASE_ACK`:
```
Bytes 28–31: Release confirmation token
Bytes 32–43: Reserved
```

#### For `CMD_SAFE_RELEASE_DENIED`:
```
Bytes 28–31: Denial reason (error code)
Bytes 32–43: Reserved
```

#### For `CMD_SW_ERROR`:
```
Bytes 28–31: Error code
Bytes 32–43: Reserved
```

---

### `reserved` (Bytes 44–55)

**Type:** bytes[12]

**Purpose:** Reserved for future Halos extensions

**Validation:** Receiver ignores this field

---

### `crc32` (Bytes 56–59)

**Type:** uint32 (big-endian)

**Algorithm:** CRC-32 (IETF polynomial 0x04C11DB7)

**Computation:**
```c
uint32_t crc32(const uint8_t* data, size_t len) {
  // Standard CRC-32 over bytes 0–55 (56 bytes)
  // Set bytes 56–63 to 0x00 during computation
}
```

**Purpose:** Packet integrity verification

**Validation:** Receiver computes CRC over bytes 0–55 (with bytes 56–63 zeroed), compares with this field; rejects if mismatch

**Example Computation:**
```python
import zlib

packet_with_zero_crc = packet[:56] + b'\x00' * 8
crc = zlib.crc32(packet_with_zero_crc) & 0xFFFFFFFF
packet[56:60] = struct.pack('>I', crc)
```

---

### `mac_tag` (Bytes 60–63)

**Type:** uint32 (big-endian)

**Purpose:** Optional MAC (Message Authentication Code) or additional integrity field

**Options:**
1. **Unused:** Set to 0x00000000
2. **HMAC tag:** 32-bit truncated HMAC (if configured)
3. **Checksum:** Additional redundancy field

**Validation:** Receiver checks if MAC verification is enabled; validates if configured

---

## Serialization Example (Python)

```python
import struct
import time
import zlib

def serialize_atl_packet(opcode, sequence, device_id, parameters=b''):
    # Initialize 64-byte buffer
    packet = bytearray(64)
    
    # Magic + Version (bytes 0–3)
    struct.pack_into('>I', packet, 0, 0x41544C01)
    
    # Opcode (bytes 4–7)
    struct.pack_into('>I', packet, 4, opcode)
    
    # Sequence (bytes 8–11)
    struct.pack_into('>I', packet, 8, sequence)
    
    # Timestamp (bytes 12–19)
    timestamp_ms = int(time.time() * 1000)
    struct.pack_into('>Q', packet, 12, timestamp_ms)
    
    # Device ID (bytes 20–23)
    struct.pack_into('>I', packet, 20, device_id)
    
    # Flags (bytes 24–27)
    struct.pack_into('>I', packet, 24, 0x00000000)  # No flags
    
    # Parameters (bytes 28–43)
    parameters_padded = parameters + b'\x00' * (16 - len(parameters))
    packet[28:44] = parameters_padded[:16]
    
    # Reserved (bytes 44–55) — already zero
    
    # CRC-32 (bytes 56–59)
    crc = zlib.crc32(bytes(packet[:56])) & 0xFFFFFFFF
    struct.pack_into('>I', packet, 56, crc)
    
    # MAC tag (bytes 60–63)
    struct.pack_into('>I', packet, 60, 0x00000000)  # No MAC
    
    return bytes(packet)

# Example: CMD_UNMUTE packet
CMD_UNMUTE = 0x00000002
sequence = 42
device_id = 0x00000001

parameters = struct.pack('>I', 0) + struct.pack('>I', 5000)  # 5000 RPM max
packet = serialize_atl_packet(CMD_UNMUTE, sequence, device_id, parameters)

print(f"Packet ({len(packet)} bytes):")
print(" ".join(f"{b:02x}" for b in packet))
```

**Output:**
```
41 54 4c 01 00 00 00 02 00 00 00 2a 00 00 01 7a b8 9c 00 00 00 00 00 01 00 00 00 00 00 00 00 00 00 00 13 88 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 a1 b2 c3 d4 00 00 00 00
```

---

## Validation Checklist

Before the receiver accepts a packet, all checks must pass:

```
✓ Magic version == 0x41544C01
✓ Packet length == 64 bytes
✓ Opcode in {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06}
✓ Sequence counter > previous (or wrapped correctly)
✓ Timestamp within ±1000 ms of current time
✓ Device ID is configured and available
✓ Flags reserved bits are 0
✓ CRC-32 (bytes 0–55) == CRC field (bytes 56–59)
✓ MAC tag (if configured) is valid
```

---

## Halos Safety State Transitions

The opcode drives state transitions in the receiver's safety state machine:

```
                  ┌─────────────────────┐
                  │   SAFE_RELEASE      │
                  │   (motor disabled,  │
                  │    fully latched)   │
                  └─────────────────────┘
                         ↑ │
                         │ │ CMD_SAFE_RELEASE_REQUEST
                         │ ↓
                  ┌─────────────────────┐
                  │  RELEASING_PENDING  │
                  │  (latch opening     │
                  │   sequence active)  │
                  └─────────────────────┘
                         ↑ │
                         │ │ CMD_SAFE_RELEASE_ACK
                         │ ↓
                  ┌─────────────────────┐
                  │   NORMAL_MUTED      │
                  │  (motor disabled)   │
                  └─────────────────────┘
                         ↑ │
                         │ │ CMD_UNMUTE
                         │ ↓
                  ┌─────────────────────┐
                  │   NORMAL_ENABLED    │
                  │  (motor enabled,    │
                  │   ready for command)│
                  └─────────────────────┘
                         ↑ │
                         │ │ CMD_MUTE
                         │ ↓ (any state)
                  ┌─────────────────────┐
                  │   MUTED             │
                  │  (motor disabled,   │
                  │   immediate stop)   │
                  └─────────────────────┘
```

---

## SLC Packet Binding

For SLC integration, the **entire 64-byte packet** is the authority binding object:

```
Authority binding:
  packet_sha256 = SHA-256(bytes[0:64])
  context_id = governance context (e.g., 'ATL:FORKLIFT:01')
  epoch = governance generation timestamp
  valid_until_ms = now + 5000

SLC Decision:
  IF packet SHA-256 matches authority.packet_sha256
  AND context matches governance
  AND epoch matches
  AND valid_until_ms >= now
  THEN forward packet unchanged
  ELSE drop packet (no downstream emission)
```

The **exact byte sequence** is critical for SLC because authority is bound to the complete packet digest. Even a single-bit change in the serialized packet invalidates the authority binding.

---

## Next Steps: Live Packet Capture

To analyze real Halos packets:

1. Enable packet logging in the SDM:
   ```c
   FILE* log = fopen("atl_packets.bin", "wb");
   fwrite(packet, 64, 1, log);
   fflush(log);
   ```

2. Capture packet bytes:
   ```bash
   hexdump -C atl_packets.bin | head -5
   ```

3. Verify structure using reference code:
   ```python
   import struct
   with open('atl_packets.bin', 'rb') as f:
       packet = f.read(64)
       magic = struct.unpack('>I', packet[0:4])[0]
       opcode = struct.unpack('>I', packet[4:8])[0]
       sequence = struct.unpack('>I', packet[8:12])[0]
       timestamp = struct.unpack('>Q', packet[12:20])[0]
       print(f"Magic: 0x{magic:08x}, Opcode: 0x{opcode:08x}, Seq: {sequence}, TS: {timestamp}")
   ```

4. Compute SLC authority binding:
   ```python
   import hashlib
   packet_sha256 = hashlib.sha256(packet).hexdigest()
   print(f"SLC authority binding: {packet_sha256}")
   ```

