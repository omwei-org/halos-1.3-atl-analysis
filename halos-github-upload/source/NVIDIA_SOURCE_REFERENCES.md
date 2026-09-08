# NVIDIA Halos 1.3 Source References

## Status: Access-Restricted

The actual NVIDIA Halos 1.3 source code is distributed in access-restricted packages on NGC (NVIDIA GPU Cloud). This document references the documented locations where these files should exist after extracting `psf-desktop.deb` and `psf-desktop-dev.deb`.

**Note:** The extraction and analysis in this bundle is based on NVIDIA's published documentation. The actual source files have not been examined due to access restrictions.

---

## Halos 1.3 Package Information

### Packages

| Package | Purpose | Size | Contains |
|---------|---------|------|----------|
| `psf-desktop.deb` | Halos 1.3 runtime binaries | ~150MB | ATL libraries, command receiver, safety runtime |
| `psf-desktop-dev.deb` | Halos 1.3 development files | ~500MB | Headers, source examples, reference implementation |

### Access

- **Registry:** NVIDIA NGC
- **Resource:** `nvidia/halos-outside-in/outside-in-safety`
- **Versions:** 
  - `nv-psf-halos-1.3-x86-lin64-release-6932895-psf-desktop`
  - `nv-psf-halos-1.3-x86-lin64-release-6932895-psf-desktop-dev`
- **Status:** Access-restricted (requires NVIDIA developer account + authorization)

### Extraction

```bash
# After obtaining packages from NGC
dpkg-deb -x psf-desktop.deb /opt/nvidia/psf/
dpkg-deb -x psf-desktop-dev.deb /opt/nvidia/psf-dev/

# Verify extraction
find /opt/nvidia/psf -name "atl_cmd_pkt.h" -o -name "cmd_rx.cpp"
```

---

## Expected File Locations

### ATL Packet Definition

**File:** `atl_cmd_pkt.h`

**Expected Paths:**
```
/opt/nvidia/psf/include/atl_cmd_pkt.h              (runtime)
/opt/nvidia/psf-dev/include/atl_cmd_pkt.h          (dev)
/opt/nvidia/psf/examples/apps/metropolis/atl/include/atl_cmd_pkt.h  (reference)
```

**Contents:**
- `struct atl_cmd_pkt_t` — 64-byte packet definition
- Opcode enum: `CMD_MUTE`, `CMD_UNMUTE`, `CMD_SAFE_RELEASE_*`, `CMD_SW_ERROR`
- Field definitions: `opcode`, `sequence`, `timestamp_ms`, `device_id`, `crc32`, etc.
- Serialization helpers: `pack_packet()`, `unpack_packet()`

**Expected Size:** ~5–10 KB

---

### SDM (Semantic Decision Module) Source

**Files:**
```
/opt/nvidia/psf/examples/apps/metropolis/atl/sdm/ccplex/ATLControl.cpp
/opt/nvidia/psf/examples/apps/metropolis/atl/sdm/ccplex/ATLControl.h
/opt/nvidia/psf/examples/apps/metropolis/atl/sdm/ccplex/SDMState.h
```

**Contents:**
- `class SDM` or `class ATLControl` — main SDM class
- `void emit_command(atl_cmd_pkt_t* pkt)` — packet emission interface
- `opcode_t select_opcode(decision_t)` — decision → opcode mapping
- `void serialize_packet(pkt, opcode, params)` — packet serialization logic
- `sequence_counter_t` — sequence counter state
- `safe_state_latch_t` — safe-state latch management

**Expected Size:** ~20–50 KB total

**Key Functions (from documentation):**
```c
// Opcode selection
opcode_t select_opcode(decision_t decision, safe_state_latch_t latch) {
  if (decision == RESTRICTIVE) return CMD_MUTE;
  if (decision == PERMISSIVE && latch == LATCHED) return CMD_SAFE_RELEASE_REQUEST;
  if (decision == PERMISSIVE && latch == RELEASING) return CMD_SAFE_RELEASE_ACK;
  return CMD_UNMUTE;
}

// Packet serialization
void serialize_packet(atl_cmd_pkt_t* pkt, opcode_t opcode, params_t params) {
  pkt->magic_version = 0x41544C01;
  pkt->opcode = (uint32_t)opcode;
  pkt->sequence = ++sequence_counter;
  pkt->timestamp_ms = current_time_ms();
  pkt->device_id = DEVICE_ID;
  pkt->flags = 0x00;
  memcpy(pkt->parameters, &params, sizeof(params));
  pkt->crc32 = compute_crc32(pkt, 56);  // CRC over bytes 0-55
}
```

---

### ATL Command Receiver Source

**Files:**
```
/opt/nvidia/psf/examples/apps/metropolis/atl/udp_cmd_receiver/cmd_rx.cpp
/opt/nvidia/psf/examples/apps/metropolis/atl/udp_cmd_receiver/cmd_rx.h
/opt/nvidia/psf/examples/apps/metropolis/atl/udp_cmd_receiver/packet_validator.h
```

**Contents:**
- `class CommandReceiver` or `class ATLReceiver` — main receiver class
- `void listen(port_t port)` — UDP socket setup
- `bool validate_crc(packet)` — CRC validation
- `bool validate_sequence(packet)` — sequence counter check
- `bool validate_freshness(packet)` — timestamp freshness check
- `bool validate_heartbeat()` — keep-alive validation
- `void dispatch_opcode(opcode_t)` — command dispatch logic

**Expected Size:** ~30–70 KB total

**Key Functions (from documentation):**
```c
// Receiver ingress loop
void CommandReceiver::listen(uint16_t port) {
  socket = udp_bind(port);
  while (running) {
    packet = udp_receive(socket, timeout);
    
    if (validate_crc(packet) &&
        validate_sequence(packet) &&
        validate_freshness(packet) &&
        validate_heartbeat()) {
      
      opcode_t op = parse_opcode(packet);
      dispatch_opcode(op);
    }
  }
}

// CRC validation
bool validate_crc(atl_cmd_pkt_t* pkt) {
  uint32_t computed = compute_crc32(pkt, 56);
  return computed == pkt->crc32;
}

// Sequence validation
bool validate_sequence(atl_cmd_pkt_t* pkt) {
  if (pkt->sequence <= last_sequence) {
    if (!(is_sequence_wrap(last_sequence, pkt->sequence))) {
      return false;  // Reject replay / out-of-order
    }
  }
  last_sequence = pkt->sequence;
  return true;
}

// Freshness validation
bool validate_freshness(atl_cmd_pkt_t* pkt) {
  uint64_t now = current_time_ms();
  int64_t age = now - pkt->timestamp_ms;
  return (age >= 0 && age <= MAX_AGE_MS);  // e.g., MAX_AGE_MS = 1000
}
```

---

### Safety Element Interface (SEI) Source

**Files:**
```
/opt/nvidia/psf/examples/apps/metropolis/sei/SafetyElementInterface.cpp
/opt/nvidia/psf/examples/apps/metropolis/sei/SafetyElementInterface.h
/opt/nvidia/psf/examples/apps/metropolis/sei/SafetyPolicy.h
```

**Contents:**
- `class SafetyElementInterface` — main SEI class
- `decision_t decide(perception_state_t)` — decision logic
- `SafetyPolicy` — safety rules engine
- Perception state aggregation and validation

**Expected Size:** ~40–80 KB total

---

### Perception Control Module (PCM) / SAIM Source

**Files:**
```
/opt/nvidia/psf/examples/apps/metropolis/pcm/PerceptionControlModule.cpp
/opt/nvidia/psf/examples/apps/metropolis/pcm/PerceptionControlModule.h
/opt/nvidia/psf/examples/apps/metropolis/saim/SafetyAlgorithmIntegration.cpp
/opt/nvidia/psf/examples/apps/metropolis/saim/SafetyAlgorithmIntegration.h
```

**Contents:**
- Perception data processing
- Sensor fusion logic
- Algorithm integration interfaces

**Expected Size:** ~100–200 KB total

---

## Build & Integration Files

### CMakeLists or Build Configuration

**Files:**
```
/opt/nvidia/psf/examples/apps/metropolis/CMakeLists.txt
/opt/nvidia/psf/examples/apps/metropolis/atl/CMakeLists.txt
/opt/nvidia/psf/examples/apps/metropolis/atl/sdm/CMakeLists.txt
/opt/nvidia/psf/examples/apps/metropolis/atl/udp_cmd_receiver/CMakeLists.txt
```

**Purpose:** Build system configuration for compiling examples and reference implementations

---

### Example Applications

**Files:**
```
/opt/nvidia/psf/examples/apps/metropolis/atl/examples/simple_receiver_test.cpp
/opt/nvidia/psf/examples/apps/metropolis/atl/examples/sdm_packet_generator.cpp
/opt/nvidia/psf/examples/apps/metropolis/atl/examples/e2e_integration_test.cpp
```

**Purpose:** Reference implementations for:
- Standalone command receiver
- Packet generation and serialization
- End-to-end test scenarios

---

## Documentation Files

### API Reference

**Files:**
```
/opt/nvidia/psf/docs/atl_api_reference.md
/opt/nvidia/psf/docs/packet_format_spec.md
/opt/nvidia/psf/docs/integration_guide.md
```

**Contents:** API documentation, packet format specification, integration steps

### Examples & Tutorials

**Files:**
```
/opt/nvidia/psf/examples/README.md
/opt/nvidia/psf/examples/atl/quick_start.md
/opt/nvidia/psf/examples/atl/packet_validation_example.md
```

---

## Key Symbols & Functions to Search For

When examining the actual source, look for these identifiers:

### Opcodes

```c
#define CMD_MUTE                      0x00000001
#define CMD_UNMUTE                    0x00000002
#define CMD_SAFE_RELEASE_REQUEST      0x00000003
#define CMD_SAFE_RELEASE_ACK          0x00000004
#define CMD_SAFE_RELEASE_DENIED       0x00000005
#define CMD_SW_ERROR                  0x00000006
```

### Packet Structure

```c
typedef struct {
  uint32_t magic_version;    // 0x41544C01
  uint32_t opcode;
  uint32_t sequence;
  uint64_t timestamp_ms;
  uint32_t device_id;
  uint32_t flags;
  uint8_t  parameters[16];
  uint8_t  reserved[12];
  uint32_t crc32;
  uint32_t mac_tag;
} atl_cmd_pkt_t;
```

### Core Functions

```c
// SDM
atl_cmd_pkt_t* sdm_generate_packet();
void sdm_emit_command(atl_cmd_pkt_t* pkt);

// Receiver
bool atl_validate_crc(atl_cmd_pkt_t* pkt);
bool atl_validate_sequence(atl_cmd_pkt_t* pkt);
bool atl_validate_freshness(atl_cmd_pkt_t* pkt);
void atl_dispatch_command(atl_cmd_pkt_t* pkt);

// Safety
decision_t sei_decide(perception_state_t* perception);
opcode_t sdm_select_opcode(decision_t decision);
```

---

## SLC Integration Points

### Recommended Integration Locations

1. **Wrapper around `SDM::emit_command()`:**
   - Intercept packet before transmission
   - Apply SLC gate logic
   - Forward or drop

2. **Pre-filter in `CommandReceiver::listen()`:**
   - Intercept received packet
   - Validate SLC authority
   - Process or drop

3. **UDP socket hook (advanced):**
   - Intercept system-level `sendto()` call
   - Check if destination is ATL receiver
   - Apply SLC gate

---

## Verification Steps (After Extraction)

Once you have the actual packages:

1. **Verify package contents:**
   ```bash
   dpkg-deb -c psf-desktop-dev.deb | grep -E "atl_cmd_pkt|cmd_rx|ATLControl"
   ```

2. **Extract and list:**
   ```bash
   dpkg-deb -x psf-desktop-dev.deb /tmp/psf-extract/
   find /tmp/psf-extract -name "*.h" -o -name "*.cpp" | head -20
   ```

3. **Search for key symbols:**
   ```bash
   grep -r "CMD_MUTE\|atl_cmd_pkt_t\|validate_crc" /tmp/psf-extract/opt/
   ```

4. **Inspect packet structure:**
   ```bash
   grep -A 20 "typedef struct" /tmp/psf-extract/opt/nvidia/psf/*/include/atl_cmd_pkt.h
   ```

5. **Verify receiver implementation:**
   ```bash
   grep -n "CommandReceiver\|listen\|recvfrom" /tmp/psf-extract/opt/nvidia/psf/*/udp_cmd_receiver/*.cpp
   ```

---

## Reference Implementation (PoC)

The SLC gate reference implementation is provided in this bundle:

- `slc_halos_adapter.py` — Core gate logic (Python)
- `slc_udp_gate.py` — Standalone UDP gate (Python)

These are research-quality implementations and should be adapted for production use with actual NVIDIA source once available.

---

## Next Steps

1. **Obtain access** to NGC packages (developer account required)
2. **Extract packages** using documented procedures
3. **Verify file locations** match expected paths in this document
4. **Inspect actual source** to confirm packet structure and flow
5. **Adapt SLC gate** using reference implementation as template
6. **Run decisive experiment** per integration-point.md
7. **Document findings** for safety certification (if applicable)

