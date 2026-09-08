# KRITICKÁ ANALÝZA: Co je FAKT vs. REKONSTRUKCIA vs. NÁVRH

## Status Dokumentu

Tento dokument jasne deľuje:
- **VERIFIED** — Priamo overené v dostupných zdrojoch
- **DOCUMENTED** — Pouze z NVIDIA PSF dokumentácie (nie v dostupnom source code)
- **INFERRED** — Logická rekonštrukcia z dostupných informácií
- **PROPOSED** — Návrh SLC gate (nie časť Halos)

---

## 1. VERIFIED: Co je NAOZAJ v Debian Package

### Package: `psf-oss-sources_1.0.0+halos-1.3+amd64+202607281657_amd64.deb`

**Obsah:** Debian base system OSS sources (bez Halos source)

**Overené:**
```bash
$ tar -tzf halos-work/halos-src/oss-sources-halos-1.3-amd64-202607281657.tar.gz | \
  head -20

adduser_3.137ubuntu1.dsc
adduser_3.137ubuntu1.tar.xz
apparmor_4.0.1really4.0.1-0ubuntu0.24.04.7.debian.tar.xz
cron_3.0pl1-184ubuntu2.debian.tar.xz
cryptsetup_2.7.0-1ubuntu4.2.debian.tar.xz
glibc_2.39-0ubuntu8.8.debian.tar.xz
json-c_0.17-1build1.debian.tar.xz
kmod_31+20240202-2ubuntu7.2.debian.tar.xz
librdkafka_2.3.0-1build2.debian.tar.xz
lvm2_2.03.16-3ubuntu3.2.debian.tar.xz
protobuf_3.21.12-8.2ubuntu0.3.debian.tar.xz
rsyslog_8.2312.0-3ubuntu9.3.debian.tar.xz
sudo_1.9.15p5-3ubuntu5.24.04.2.debian.tar.xz
systemd_255.4-1ubuntu8.16.debian.tar.xz
util-linux_2.39.3-9ubuntu6.5.debian.tar.xz
zlib_1.3.dfsg-3.1ubuntu2.1.debian.tar.xz
```

**FAKT:** Žiadny `atl_cmd_pkt.h`, žiadny Halos source

```bash
$ grep -r "atl_cmd_pkt\|CMD_MUTE\|atl_sdm\|SDM\|SEI\|SAIM" \
  halos-work/halos-src/ 2>/dev/null
  
# Výstup: ŽIADNY ZÁPAS
```

**FAKT:** Packet je len Debian OSS, žiadny Halos source code.

---

## 2. DOCUMENTED: Co hovorí NVIDIA PSF Dokumentácia

### Zdroj: https://developer.nvidia.com/docs/oiss/psf/index.html

NVIDIA dokumentuje:

#### 2.1. Halos Architecture
```
SIPP → SAIM/PCM → SEI → SDM → ATL Command Receiver
```

**Status:** DOKUMENTOVANÉ (nie verifikované v source)

#### 2.2. ATL Packet
- Exactly 64 bytes
- Opcode field: CMD_MUTE, CMD_UNMUTE, CMD_SAFE_RELEASE_REQUEST/ACK/DENIED, CMD_SW_ERROR
- CRC field (integrity)
- Sequence field (replay protection)
- Timestamp field (freshness)

**Status:** DOKUMENTOVANÉ (nie verifikované v source)

#### 2.3. Command Receiver
- UDP socket ingress
- CRC validation
- Sequence validation
- Freshness validation
- Safe-state latch validation
- Opcode dispatch

**Status:** DOKUMENTOVANÉ (nie verifikované v source)

#### 2.4. ATL Packet Source Files
```
/opt/nvidia/psf/examples/apps/metropolis/atl/include/atl_cmd_pkt.h
/opt/nvidia/psf/examples/apps/metropolis/atl/sdm/ccplex/ATLControl.cpp
/opt/nvidia/psf/examples/apps/metropolis/atl/udp_cmd_receiver/cmd_rx.cpp
/opt/nvidia/psf/examples/apps/metropolis/sei/SafetyElementInterface.cpp
```

**Status:** EXISTUJE PODĽA DOKUMENTÁCIE, ALE V ACCESS-RESTRICTED PACKAGE

---

## 3. INFERRED: Rekonštrukcia z Dostupných Informácií

### 3.1. Halos Execution Path

Na základe:
- NVIDIA dokumentácie (públic API docs)
- Názvy komponentov v package
- SLC PoC v0.3 reference implementation

**Rekonštrukcia:**

```
SIPP (sensors)
  ↓ [raw data]
SAIM/PCM (Safety Core)
  ↓ [processed perception]
SEI (Safety Core)
  ↓ [binary decision: PERMISSIVE | RESTRICTIVE]
SDM (Safety Core)
  ↓ [opcode selection]
    if PERMISSIVE:
      opcode = CMD_UNMUTE
    else:
      opcode = CMD_MUTE
  ↓ [serialization to 64-byte packet]
  ↓ [UDP send]
ATL Receiver (UDP listen)
  ↓ [CRC check, sequence check, freshness check, safe-state latch check]
  ↓ [opcode parsing]
  ↓ [dispatch to safety function]
Safety Function
  ↓ [actuator control]
Equipment (motor disable/enable)
```

**Status:** INFERRED z dokumentácie + komponentov

### 3.2. Packet Structure

Na základe:
- NVIDIA dokumentácie (64 bytes, opcode field, CRC field, sequence field)
- packet-format.md v bundle

**Rekonštrukcia:**

```
Bytes  0-3:  magic_version (0x41544C01 = "ATL")
Bytes  4-7:  opcode
Bytes  8-11: sequence (replay protection)
Bytes 12-19: timestamp_ms (freshness)
Bytes 20-23: device_id
Bytes 24-27: flags
Bytes 28-43: parameters
Bytes 44-55: reserved
Bytes 56-59: CRC32
Bytes 60-63: mac_tag or reserved
```

**Status:** INFERRED z NVIDIA docs + standard packet design

### 3.3. Validation Sequence in Receiver

Na základe:
- NVIDIA dokumentácie ("receiver validates CRC, sequence, freshness, etc.")
- Standard safety-critical design practices

**Rekonštrukcia:**

```
1. UDP receive on socket
2. Check packet length == 64
3. Validate CRC32(bytes 0-55) == bytes 56-59
4. Validate sequence > last_sequence (or wrapped)
5. Validate timestamp_ms is recent (< 1000ms old)
6. Validate heartbeat (regular keep-alive signals)
7. Validate safe-state latch consistency
8. Parse opcode from bytes 4-7
9. Dispatch opcode to handler
```

**Status:** INFERRED z NVIDIA docs + safety practices

---

## 4. PROPOSED: SLC Gate Návrh

### 4.1. Koncept

Tvoj návrh: **Execution-authority gate medzi SDM a receiver**

Na základe:
- Decentralizovanej governance kontroly
- Epoch-based authority revocation

**Status:** TVOJ NÁVRH (nie časť Halos)

### 4.2. Insertion Point

```
PROPOSED:

SDM (generates 64-byte packet)
  ↓
┌─────────────────────────────────┐
│    SLC Gate (NEW INSERTION)     │
│                                 │
│  Input:  packet (64 bytes)      │
│          governance state       │
│          authority database     │
│                                 │
│  Checks:                        │
│  ✓ packet size == 64            │
│  ✓ SHA256(packet) in authority  │
│  ✓ authority.epoch == gov.epoch │
│  ✓ authority.expiry > now       │
│  ✓ gov.route_permitted == true  │
│  ✓ gov.safety_permitted == true │
│                                 │
│  Decision: ALLOW | BLOCK        │
└─────────────────────────────────┘
  ↓
ATL Receiver (existing)
  ↓
Safety Function (existing)
```

**Status:** NÁVRH (nie dokumentované v Halos)

### 4.3. Why This Point?

**Dôvody:**
1. Byte preservation (packet unchanged on ALLOW)
2. No modification of Halos logic
3. Measurable at receiver ingress
4. Independent from Halos freshness/sequence
5. Clean insertion (wrapper or socket hook)

**Status:** INFERENCE + DESIGN RATIONALE (nie dokumentované)

### 4.4. Epoch-Based Revocation

**Mechanizmus:**

```
Time T0:
  Authority: epoch = 481, packet_sha256 = "abc123..."
  Governance: epoch = 481
  Result: ALLOW

Time T1 (governance revokes authority):
  Authority: epoch = 481, packet_sha256 = "abc123..." (UNCHANGED)
  Governance: epoch = 482 (ADVANCED)
  Result: BLOCK (epoch mismatch)

Same packet bytes cannot be replayed after epoch change.
```

**Status:** NÁVRH SLC mechanizmu (nie dokumentované v Halos)

---

## 5. Reference Implementation (SLC PoC v0.3)

**Zdroj:** SLC_Halos_PoC_v0_3/ (earlier research)

**Obsahuje:**
- `slc_halos_adapter.py` — Core gate logic
- `slc_udp_gate.py` — UDP gate implementation
- `demo_v03.py` — Demonstration

**Status:** EXISTUJÚCA REFERENČNÁ IMPLEMENTÁCIA (nie súčasť Halos)

---

## 6. CRUCIAL DISTINCTION: Co Chýba

### 6.1. Nie je overené v Halos source:

```
❌ Exact byte layout of atl_cmd_pkt_t
❌ Exact CRC algorithm (CRC-32? CRC-16?)
❌ Exact validation order in receiver
❌ Exact opcode selection logic in SDM
❌ Exact safe-state latch implementation
❌ Exact serialization format
```

Dôvod: Access-restricted packages (`psf-desktop.deb`, `psf-desktop-dev.deb`)

### 6.2. Dokumentované podľa NVIDIA PSF Docs:

```
✓ 64-byte packet format
✓ Opcode field exists (CMD_MUTE, CMD_UNMUTE, etc.)
✓ CRC field exists
✓ Sequence field exists (replay protection)
✓ Timestamp field exists (freshness)
✓ Receiver validates: CRC, sequence, freshness, safe-state latch
✓ Receiver dispatches opcode to safety function
✓ Path: SIPP → SAIM/PCM → SEI → SDM → Receiver
```

### 6.3. Rekonštrukcia z logiky:

```
← Packet structure (64 bytes layout)
← Validation sequence (CRC → sequence → freshness → latch)
← Opcode mapping (PERMISSIVE → CMD_UNMUTE, RESTRICTIVE → CMD_MUTE)
← Command dispatch (opcode → safety function)
```

### 6.4. Tvoj návrh (nie Halos):

```
← SLC Gate insertion point
← Authority binding mechanism (SHA-256 + context + epoch)
← Epoch-based revocation
← ALLOW/BLOCK decision logic
```

---

## 7. CRITICAL TABLE: What We Know vs. What We Don't

| Aspect | VERIFIED | DOCUMENTED | INFERRED | PROPOSED |
|--------|----------|------------|----------|----------|
| **Package contains** | Debian OSS only | — | — | — |
| **Halos exists** | No source | Yes (docs) | — | — |
| **Exec path exists** | No source | Yes (docs) | Yes | — |
| **64-byte packet** | No source | Yes (docs) | Yes | — |
| **Opcode field** | No source | Yes (docs) | Yes | — |
| **CRC validation** | No source | Yes (docs) | Yes | — |
| **Sequence check** | No source | Yes (docs) | Yes | — |
| **Freshness check** | No source | Yes (docs) | Yes | — |
| **Safe-state latch** | No source | Yes (docs) | Yes | — |
| **Receiver ingress** | No source | Yes (docs) | Yes | — |
| **SLC Gate** | — | — | — | Yes |
| **Authority binding** | — | — | — | Yes |
| **Epoch revocation** | — | — | — | Yes |

---

## 8. Decisive Experiment: What Can Be Tested?

### 8.1. Testable with Live Halos (if source obtained):

```
✓ Verify packet structure matches reconstruction
✓ Verify validation order in receiver
✓ Verify opcode dispatch logic
✓ Verify safe-state latch behavior
✓ Verify CRC algorithm
✓ Verify sequence handling
✓ Verify freshness window
```

### 8.2. Testable with SLC Gate:

```
✓ Authority binding: packet → SHA-256 digest
✓ Epoch tracking: governance epoch vs. authority epoch
✓ Revocation: epoch mismatch → BLOCK
✓ Byte preservation: ALLOW → packet unchanged
✓ Receiver measurement: packet count before/after revocation
✓ Independence: Halos remains permissive but SLC blocks
```

### 8.3. Testable Experiment Flow:

```
1. SETUP:
   - Halos emits CMD_UNMUTE (permissive)
   - SLC issues authority (epoch 481)
   - Packet forwarded → receiver accepts → motor enables

2. TRIGGER:
   - Governance epoch advances (481 → 482)

3. TEST:
   - Same packet bytes replayed
   - Halos still permissive (would emit same packet)
   - SLC blocks (epoch mismatch)
   - Receiver ingress: zero new packets

4. EVIDENCE:
   ✓ Halos decision: PERMISSIVE (logs)
   ✓ Packet bytes: identical (capture)
   ✓ Packet CRC: valid (verify)
   ✓ Receiver packets: blocked (count)
   ✓ SLC reason: EPOCH_MISMATCH (logs)
```

---

## 9. Limitations: What We Cannot Verify

```
1. Exact byte layout of atl_cmd_pkt_t
   └─ Reason: source code not accessible

2. Exact CRC algorithm (CRC-32? CRC-16? polynomial?)
   └─ Reason: source code not accessible

3. Exact serialization code in SDM
   └─ Reason: source code not accessible

4. Exact validation logic in receiver
   └─ Reason: source code not accessible

5. Exact opcode selection in SDM
   └─ Reason: source code not accessible

6. Safe-state latch implementation details
   └─ Reason: source code not accessible

7. Performance characteristics
   └─ Reason: source code and runtime not accessible

8. Production safety certification
   └─ Reason: Research PoC, not certified
```

---

## 10. What's Next: How to Verify

### 10.1. Obtain Actual Source

```bash
# Get NGC access (requires NVIDIA developer account + authorization)
ngc registry resource download-version \
  "nvidia/halos-outside-in/outside-in-safety:nv-psf-halos-1.3-x86-lin64-release-6932895-psf-desktop-dev"

# Extract
dpkg-deb -x psf-desktop-dev.deb /opt/nvidia/psf-dev/

# Verify locations
find /opt/nvidia/psf-dev -name "atl_cmd_pkt.h" -o -name "cmd_rx.cpp"

# Inspect actual structures
grep -A 30 "typedef struct" /opt/nvidia/psf-dev/opt/nvidia/psf/*/include/atl_cmd_pkt.h

# Verify CRC algorithm
grep -n "crc\|CRC" /opt/nvidia/psf-dev/opt/nvidia/psf/*/udp_cmd_receiver/cmd_rx.cpp
```

### 10.2. Test with Real Halos

```bash
# Build reference receiver from actual source
cd /opt/nvidia/psf-dev/opt/nvidia/psf/examples/apps/metropolis/atl/
make

# Run with instrumentation
./cmd_rx --port 13000 --log packets.bin

# Capture SDM packets
./sdm_gen --output packets_from_sdm.bin

# Verify structure
hexdump -C packets_from_sdm.bin | head -5
```

### 10.3. Implement SLC Gate

```bash
# Use reference implementation as template
python3 slc_halos_adapter.py

# Adapter wraps SDM emission
class SLCSDMProxy:
    def emit_command(self, packet):
        # Original SDM logic
        real_sdm.emit(packet)
        
        # SLC gate decision
        if slc_gate.decide(packet, governance):
            send_to_receiver(packet)
        else:
            log_blocked(packet)
```

### 10.4. Run Decisive Experiment

```bash
# T0: Normal operation
sdm_emit(CMD_UNMUTE)  # → receiver accepts → motor enabled
# Check: receiver packet count = 1

# T1: Revoke authority
governance.epoch += 1

# T2: Replay same packet
sdm_emit(CMD_UNMUTE)  # Same 64 bytes
# Check: SLC blocks (EPOCH_MISMATCH)
# Check: receiver packet count = 1 (unchanged)
# Check: Halos logs show decision still PERMISSIVE
```

---

## Summary: The Three Layers

### Layer 1: VERIFIED (in Debian package)
- Package contains Debian base system OSS
- No Halos source code present

### Layer 2: DOCUMENTED (NVIDIA PSF docs)
- Halos architecture: SIPP → SAIM/PCM → SEI → SDM → Receiver
- Packet: 64 bytes, opcode, CRC, sequence, timestamp
- Receiver: validates CRC, sequence, freshness, safe-state latch
- File locations (but files in access-restricted packages)

### Layer 3: INFERRED (from documentation + logic)
- Exact packet structure (byte layout)
- Exact validation order
- Exact opcode mapping
- Exact serialization logic

### Layer 4: PROPOSED (your SLC design)
- Gate insertion point
- Authority binding (SHA-256 + context + epoch)
- Epoch-based revocation
- ALLOW/BLOCK decision logic

---

## Recommendation

**Before you proceed with live integration:**

1. **Explicitly state** which layer each claim belongs to:
   - VERIFIED ← only what's in Debian package
   - DOCUMENTED ← from NVIDIA PSF docs
   - INFERRED ← reconstruction from logic
   - PROPOSED ← your SLC design

2. **Tag all diagrams and code snippets** with their layer

3. **When presenting to others, use this table** to show what's firm vs. what's speculative

4. **Plan for verification** once you obtain `psf-desktop-dev.deb`:
   - Compare actual `atl_cmd_pkt_t` against reconstruction
   - Compare actual receiver logic against inference
   - Validate CRC algorithm
   - Validate serialization

5. **For SLC design**, keep proposing layer distinct:
   - Don't claim it's "how Halos works"
   - Frame it as "independent authority gate that could be inserted here"

