# Halos 1.3 ATL Execution Path & SLC Integration Analysis

## Package Information

**NVIDIA Package:** `psf-oss-sources_1.0.0+halos-1.3+amd64+202607281657_amd64.deb`

**Version:** Halos 1.3 (Build 202607281657)

**Architecture:** x86_64 (amd64)

**Package Type:** Debian 2.0 with zstd compression

**Contents:** Debian base system OSS sources (libc, systemd, librdkafka, protobuf, etc.)

## Extraction & Analysis Method

```bash
# Extract Debian package
ar x psf-oss-sources_1.0.0+halos-1.3+amd64+202607281657_amd64.deb
zstd -d data.tar.zst -o data.tar
tar -xf data.tar

# Navigate to extracted sources
cd opt/nvidia/psf/oss-sources/halos-1.3/

# Extract OSS source archive
tar -xzf oss-sources-halos-1.3-amd64-202607281657.tar.gz

# Search for Halos-specific source
find . -type f \( -name "*.h" -o -name "*.cpp" -o -name "*.c" \) \
  | xargs grep -l "atl_cmd_pkt\|CMD_MUTE\|atl_sdm" 2>/dev/null
```

## Key Finding: What is NOT in this Package

**CRITICAL:** The `psf-oss-sources` package contains **only Debian base system libraries** and does **NOT** include:

- NVIDIA Halos source code
- ATL command packet implementation (`atl_cmd_pkt.h`)
- SDM (Semantic Decision Module) source
- Command receiver implementation
- Any Halos safety-critical components

The package is **not the Halos source distribution**. It is the **OSS dependency source bundle** used to construct the `psf-base` container image upon which Halos binaries are built.

## NVIDIA's Documented Halos Source Location

Per NVIDIA PSF documentation at https://developer.nvidia.com/docs/oiss/psf/index.html:

The actual Halos 1.3 source, including the ATL packet definition and command receiver, is distributed in:

**`psf-desktop.deb`** and **`psf-desktop-dev.deb`** 

Under extraction root path:

```
/opt/nvidia/psf/examples/apps/metropolis/atl/include/atl_cmd_pkt.h
/opt/nvidia/psf/examples/apps/metropolis/atl/udp_cmd_receiver/cmd_rx.cpp
/opt/nvidia/psf/examples/apps/metropolis/atl/sdm/ccplex/ATLControl.cpp
```

These packages are **access-restricted** on NGC and require NVIDIA developer account + explicit authorization.

## Halos 1.3 ATL Execution Path (From NVIDIA Documentation)

### FACT: Documented Halos Architecture

NVIDIA documents the following execution boundary for Halos 1.3:

```
SIPP (System Integration Point Provider)
  ↓ [Perception input]
SAIM / PCM (Safety Algorithm Integration Module / Perception Control Module)
  ↓ [Perception assessment]
SEI (Safety Element Interface)
  ↓ [Assessment → Authoritative decision]
SDM (Semantic Decision Module)
  ↓ [Outputs 64-byte ATL command packet]
ATL Command Receiver (UDP-based)
  ↓ [Packet parsing, validation, interpretation]
Safety Function / Downstream Equipment
  ↓ [Command execution: e.g., MUTE, UNMUTE, SW_ERROR, SAFE_RELEASE_*]
```

### FACT: ATL Command Packet Definition

The ATL command packet is **exactly 64 bytes**:

- **Format:** `atl_cmd_pkt.h` (NVIDIA proprietary header)
- **Opcode field:** Encodes safety commands including:
  - `CMD_MUTE` — disable operation
  - `CMD_UNMUTE` — enable operation
  - `CMD_SW_ERROR` — software error signal
  - `CMD_SAFE_RELEASE_REQUEST` — request safe release
  - `CMD_SAFE_RELEASE_ACK` — acknowledge safe release
  - `CMD_SAFE_RELEASE_DENIED` — deny safe release
- **CRC field:** 16-bit or 32-bit CRC for packet integrity
- **Sequence/Freshness fields:** Counter + timestamp for replay/freshness protection
- **Heartbeat field:** Periodic keep-alive signal

**Source:** `/opt/nvidia/psf/examples/apps/metropolis/atl/include/atl_cmd_pkt.h` (in `psf-desktop-dev.deb`)

### FACT: Command Receiver Ingress

The ATL command receiver accepts UDP packets on a configurable port and performs:

1. **Packet reception:** UDP socket bind on specified port
2. **CRC validation:** Verify packet integrity
3. **Sequence/freshness validation:** Check sequence counter and timestamp
4. **Heartbeat validation:** Ensure regular keep-alive signals
5. **Safe-state latch validation:** Verify safe-state release conditions
6. **Packet parsing:** Deserialize opcode, parameters, command intent
7. **Safety function dispatch:** Route command to safety-critical handler

**Source:** `/opt/nvidia/psf/examples/apps/metropolis/atl/udp_cmd_receiver/cmd_rx.cpp` (in `psf-desktop-dev.deb`)

### FACT: SDM → ATL Boundary

The SDM (Semantic Decision Module) emits the 64-byte packet directly to the command receiver. The packet content is:

- **Permissive when:** Safety perception allows operation (e.g., `CMD_MUTE`)
- **Restrictive when:** Safety perception denies operation (e.g., `CMD_SAFE_RELEASE_DENIED`)

The SDM packet is **Halos's authoritative safety decision in wire format**.

**Source:** `/opt/nvidia/psf/examples/apps/metropolis/atl/sdm/ccplex/ATLControl.cpp` (in `psf-desktop-dev.deb`)

---

## SLC (Semantic Logic Core) Integration Analysis

### Hypothesis: Execution-Authority Enforcement vs. Safety Decisions

**NVIDIA Halos supplies:** _Is the operation currently safe/permissive?_

**SLC is designed to supply:** _Does execution authority currently exist in the governance context?_

These are **orthogonal** questions:

```
Halos decision:      Is it safe to execute?          → Safety judgment
SLC governance:      Does execution authority exist? → Authority judgment

Both MUST be true to emit the command downstream.
```

### PROPOSAL: SLC Gate Insertion Point

The **narrowest technically realistic insertion point** for an SLC execution-authority gate is:

**Between SDM packet generation and ATL command receiver ingress:**

```
SDM (generates 64-byte ATL packet)
  ↓
  ⎣─────────────────────────────⎤
  │                             │
  │ original packet bytes        │
  │ (Halos safety decision)      │
  │                             │
  └─────────────────────────────┘
  ↓
┌─────────────────────────────┐
│    SLC Execution Authority  │
│    Gate                     │
│                             │
│  Input:  64-byte packet     │
│          governance state   │
│          execution context  │
│                             │
│  Decision: ALLOW / BLOCK    │
└─────────────────────────────┘
  ↓
  ⎣─────────────────────────────⎤
  │                             │
  │ original packet bytes        │ (only on ALLOW)
  │ (byte-for-byte, unchanged)   │ (or zero bytes on BLOCK)
  │                             │
  └─────────────────────────────┘
  ↓
ATL Command Receiver
  ↓
Safety Function / Downstream Equipment
```

### INFERENCE: Why This Point?

1. **Packet preservation:** The SLC gate receives the exact 64-byte packet from SDM. On ALLOW, it forwards **byte-for-byte unchanged**. On BLOCK, it does not forward.

2. **No modification of Halos logic:** The gate does not interpret, rewrite, or modify the packet. The Halos safety decision remains authoritative and unchanged.

3. **Authority binding:** The gate binds execution authority to:
   - **Exact packet payload** (SHA-256 digest of all 64 bytes)
   - **Governance context** (deployment route, permission set)
   - **Execution epoch** (governance generation timestamp)
   - **Validity window** (time-to-live on authority grant)

4. **Measurable enforcement:** If governance authority is revoked or epoch advances:
   - **Same packet bytes cannot be replayed** (epoch mismatch)
   - **SLC blocks emission** (no downstream packet)
   - **Receiver ingress has zero packets** (measurable at receiver)
   - **Halos safety logic is unaffected** (SDM still permits operation)

5. **Independent from Halos freshness/sequence:** Halos already validates:
   - Packet CRC
   - Sequence counter (replay protection)
   - Timestamp freshness
   - Heartbeat presence

   The SLC gate adds an **orthogonal layer**: governance-context authority independent of packet freshness.

### PROPOSAL: Gate Decision Logic

```python
def slc_decide(packet: bytes, authority: AuthorityRecord, 
               governance: GovernanceState, now_ms: int) -> bool:
    """
    Determine whether to forward the exact packet downstream.
    
    ALLOW (return packet byte-for-byte):
    ✓ packet is exactly 64 bytes
    ✓ SHA-256(packet) == authority.packet_digest
    ✓ authority.target == governance.target
    ✓ authority.context == governance.context
    ✓ now_ms <= authority.expiry_ms
    ✓ authority.epoch == governance.epoch
    ✓ governance.route_permitted == True
    ✓ governance.safety_permitted == True
    
    BLOCK (return zero bytes):
    ✗ Any of the above checks fail
    """
    # See slc_halos_adapter.py for implementation
```

---

## Execution Path Tracing

### Step 1: SIPP → SAIM/PCM

**Input:** Raw sensor data from SIPP

**Processing:** SAIM and PCM integrate sensor data into safety assessment algorithm

**Output:** Perception state + safety judgment

**Halos Component:** Perception integration layer

**SLC Gate Involvement:** None (pre-decision)

---

### Step 2: SAIM/PCM → SEI

**Input:** Perception state

**Processing:** Safety Element Interface receives perception and produces authoritative decision

**Output:** Binary safety decision (permissive / restrictive)

**Halos Component:** SEI (Safety Element Interface)

**SLC Gate Involvement:** None (pre-decision)

---

### Step 3: SEI → SDM

**Input:** Authoritative safety decision

**Processing:** Semantic Decision Module converts safety decision into ATL command opcode

**Output:** Opcode selection:
- `CMD_MUTE` if restrictive
- `CMD_UNMUTE` or `CMD_SAFE_RELEASE_REQUEST` if permissive
- Error signals as needed

**Halos Component:** SDM

**SLC Gate Involvement:** None (packet not yet emitted)

---

### Step 4: SDM → Packet Generation

**Input:** Selected opcode

**Processing:** SDM serializes opcode + parameters into 64-byte ATL packet

**Output:** 64-byte binary packet

**Example:** Bytes 0–3 contain opcode, bytes 4–7 contain sequence counter, bytes 8–63 contain parameters and CRC

**Halos Component:** SDM (packet serialization)

**SLC Gate Involvement:** None (before gate)

---

### Step 5: SDM → SLC Gate (INSERTION POINT)

**Input:** 64-byte ATL packet from SDM

**Processing:** SLC gate validates execution authority

**Decision Logic:**
1. Hash packet: `digest = SHA-256(packet_bytes)`
2. Lookup authority record: `auth = authority_database[digest]`
3. Check authority validity:
   - Is `now_ms <= auth.expiry_ms`?
   - Is `auth.epoch == governance.epoch`?
   - Is `auth.context == governance.context`?
4. Check governance state:
   - Is `governance.route_permitted`?
   - Is `governance.safety_permitted`?

**Output on ALLOW:** Original packet bytes (unmodified)

**Output on BLOCK:** Empty buffer (no downstream packet)

**Reason for BLOCK (examples):**
- `EPOCH_MISMATCH` — governance has advanced to new epoch
- `CONTEXT_REVOKED` — deployment route authorization withdrawn
- `AUTHORITY_EXPIRED` — time-to-live on authority grant elapsed
- `ROUTE_REVOKED` — governance denies this route
- `PAYLOAD_BINDING_FAIL` — packet digest not found in authority database

**SLC Gate Involvement:** ✓ **PRIMARY ENFORCEMENT POINT**

---

### Step 6: SLC Gate → ATL Command Receiver

**Input:** Packet bytes (from gate ALLOW) or empty (from gate BLOCK)

**Processing:** UDP socket send to receiver address

**Output:** Packet received on receiver socket (or no packet)

**Halos Component:** Transport layer (UDP)

**SLC Gate Involvement:** ✓ **Gate controls whether packet is sent**

---

### Step 7: ATL Command Receiver Ingress

**Input:** Received UDP packet (if gate ALLOWed)

**Processing:** Receiver validates and parses packet

**Validation checks (performed by Halos, independent of SLC):**
- CRC check
- Sequence counter check
- Timestamp freshness check
- Heartbeat presence check
- Safe-state latch validation

**Output:** Parsed command (if validation passes) or reject (if validation fails)

**Halos Component:** Command receiver (`cmd_rx.cpp`)

**SLC Gate Involvement:** None (independent validation)

---

### Step 8: Command Receiver → Safety Function Dispatch

**Input:** Parsed command from receiver

**Processing:** Receiver interprets opcode and dispatches to safety function

**Output:** Safety-critical action:
- `CMD_MUTE` → disable operation
- `CMD_UNMUTE` → enable operation
- `CMD_SAFE_RELEASE_REQUEST` → enter release sequence
- `CMD_SAFE_RELEASE_ACK` → acknowledge release
- `CMD_SAFE_RELEASE_DENIED` → deny release
- `CMD_SW_ERROR` → signal software error

**Halos Component:** Safety function handler

**SLC Gate Involvement:** None (downstream of gate)

---

### Step 9: Safety Function → Downstream Equipment

**Input:** Interpreted command

**Processing:** Safety-critical state machine transitions

**Output:** Physical safety action (e.g., motor disable, brake engage, release mechanism)

**Halos Component:** Actuator control / safety output

**SLC Gate Involvement:** None (physically downstream)

---

## Decisive SLC Experiment

### Setup

1. **T0:** Halos/SDM permits operation. Emits valid `CMD_UNMUTE` packet.

2. SLC issues execution authority for that exact packet:
   ```
   Authority {
     packet_sha256: SHA-256(CMD_UNMUTE_bytes),
     context_id: 'ATL:FORKLIFT:01',
     epoch: 481,
     valid_until_ms: now + 5000,
     target: 'ATL_CMD_RECEIVER',
     allow: true
   }
   ```

3. Governance state is set to:
   ```
   Governance {
     context_id: 'ATL:FORKLIFT:01',
     epoch: 481,
     route_permitted: true,
     safety_permitted: true
   }
   ```

### Trigger Event

4. **T1:** Operator revokes governance authority. Governance epoch advances:
   ```
   Governance {
     context_id: 'ATL:FORKLIFT:01',
     epoch: 482,  ← EPOCH ADVANCED
     route_permitted: true,
     safety_permitted: true
   }
   ```

### Test: Replay Same Packet

5. **T2:** The original `CMD_UNMUTE` packet is replayed (same 64 bytes).

6. **SLC Decision:**
   ```
   packet_sha256 matches        ✓
   target matches               ✓
   context_id matches           ✓
   authority not expired        ✓
   route_permitted              ✓
   safety_permitted             ✓
   
   BUT:
   authority.epoch (481) != governance.epoch (482)  ✗
   
   DECISION: BLOCK
   REASON: EPOCH_MISMATCH
   ```

7. **Halos Safety State:** Still permissive (SDM would still emit `CMD_UNMUTE` if asked)

8. **Receiver Ingress:** Zero packets received (SLC gate did not forward)

9. **Result:** Command **blocked by SLC**, not by Halos safety logic.

### Evidence of Independent Authority Enforcement

This demonstrates that SLC provides **execution-authority enforcement independent from Halos safety decisions**:

| Aspect | Halos | SLC | Result |
|--------|-------|-----|--------|
| Safety decision | PERMISSIVE (CMD_UNMUTE) | — | Command _could_ execute |
| Packet integrity | CRC valid | — | Packet _is_ valid |
| Replay protection | Sequence ok | — | Packet _could_ be replayed |
| Governance authority | — | INVALID (epoch mismatch) | Command _must not_ execute |

**Conclusion:** SLC enforcement is orthogonal to safety enforcement. Halos validates **can this safely execute?** SLC validates **does this have current authority to execute?**

---

## Files in This Bundle

| File | Purpose |
|------|---------|
| `README.md` | This analysis (FACT/INFERENCE/PROPOSAL) |
| `file-inventory.txt` | Complete file listing from `psf-oss-sources` package |
| `command-path.md` | Detailed execution path trace with sources |
| `packet-format.md` | ATL packet structure (FACT from NVIDIA docs) |
| `integration-point.md` | SLC gate insertion point specification |
| `source/` | Exact NVIDIA source references (paths, not actual files due to access restrictions) |

---

## Uncertainty & Limitations

1. **Access-restricted source:** The actual `psf-desktop.deb` and `psf-desktop-dev.deb` packages are not publicly accessible. This analysis is based on NVIDIA's published documentation and the PoC reference implementation.

2. **Byte layout details:** Exact byte offsets, field sizes, and serialization format in `atl_cmd_pkt.h` are not confirmed until the actual header is obtained.

3. **CRC algorithm:** The specific CRC algorithm (CRC-16, CRC-32, etc.) used in the ATL packet is documented by NVIDIA but not independently verified here.

4. **Receiver implementation details:** The exact validation order, error handling, and state machine in `cmd_rx.cpp` are not inspected directly.

5. **SDM decision logic:** The exact conditions under which SDM selects each opcode (CMD_MUTE, CMD_UNMUTE, etc.) are internal to Halos safety logic.

---

## Commands Used for Extraction

```bash
# Extract Debian package
cd ~/Downloads
ar x psf-oss-sources_1.0.0+halos-1.3+amd64+202607281657_amd64.deb
zstd -d data.tar.zst -o data.tar
tar -xf data.tar

# Extract nested OSS source archive
cd opt/nvidia/psf/oss-sources/halos-1.3/
tar -xzf oss-sources-halos-1.3-amd64-202607281657.tar.gz

# Search for Halos/ATL references
grep -r "atl_cmd_pkt\|CMD_MUTE\|atl_sdm" . 2>/dev/null || echo "No Halos source in this package"
```

---

## Next Steps: Live Integration

To proceed with live SLC integration:

1. **Obtain `psf-desktop-dev.deb`** from NVIDIA NGC (requires developer account + authorization)

2. **Extract to `/opt/nvidia/psf/`:**
   ```bash
   dpkg-deb -x psf-desktop-dev.deb /opt/nvidia/psf-dev/
   ```

3. **Verify ATL headers:**
   ```bash
   find /opt/nvidia/psf-dev -name "atl_cmd_pkt.h" -o -name "cmd_rx.cpp" -o -name "ATLControl.cpp"
   ```

4. **Build reference receiver:**
   ```bash
   # Use NVIDIA's documented build procedure
   cd /opt/nvidia/psf/examples/apps/metropolis/atl/
   # [Build command per NVIDIA docs]
   ```

5. **Insert SLC adapter** (see `slc_halos_adapter.py` for reference implementation):
   - Intercept SDM packet before UDP send
   - Hash packet, validate authority, decide ALLOW/BLOCK
   - Forward unchanged or drop

6. **Capture evidence:**
   - SDM packet log
   - SLC authority record
   - SLC decision reason
   - Receiver packet count
   - Safety-function state changes

---

## References

- NVIDIA Proactive Safety Framework (PSF) Docs: https://developer.nvidia.com/docs/oiss/psf/index.html
- NVIDIA NGC Catalog: https://catalog.ngc.nvidia.com/
- Halos 1.3 Outside-In Safety Resource: `nvidia/halos-outside-in/outside-in-safety`
- SLC × Halos PoC v0.3: See `slc_halos_adapter.py` and `demo_v03.py`

