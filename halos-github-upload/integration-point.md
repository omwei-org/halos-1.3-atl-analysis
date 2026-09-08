# SLC Integration Point Specification

## Executive Summary

**Primary Insertion Point:** Between SDM packet generation and ATL command receiver ingress

**Architecture:**
```
SDM (generates 64-byte ATL packet)
  ↓
SLC Gate ← INSERTION POINT
  ↓
ATL Command Receiver
```

**Gate Properties:**
- **Input:** Original 64-byte packet from SDM
- **Decision:** ALLOW (forward) or BLOCK (drop)
- **Output (ALLOW):** Original packet bytes, unchanged
- **Output (BLOCK):** No downstream transmission
- **Authority Binding:** SHA-256(exact_64_bytes) + governance context + execution epoch

---

## Why This Point is Optimal

### 1. Packet Preservation

The gate intercepts the packet **before any modification or transmission**. On ALLOW decision:

```c
// SLC gate pseudocode
if (decision == ALLOW) {
    // Forward exact packet bytes without modification
    send_to_receiver(original_packet);  // All 64 bytes identical
} else {
    // Drop packet; no downstream transmission
    return;
}
```

**Consequence:** Halos's packet remains byte-for-byte identical. No modification of the safety decision.

### 2. No Modification of Halos Logic

The gate does not:
- Interpret the opcode
- Rewrite any fields
- Modify the CRC
- Change sequence counter
- Alter timestamp

The gate only:
- Hashes the complete packet
- Checks authority binding (digest + context + epoch)
- Makes a binary forwarding decision

**Consequence:** Halos safety logic is **completely unaffected**. The safety decision remains authoritative.

### 3. Independent Authority Enforcement

The gate enforces **execution authority** independent from Halos **safety decisions**:

| Aspect | Halos | SLC | Combined Effect |
|--------|-------|-----|---|
| Safety Decision | Permissive (CMD_UNMUTE) | — | Command *could* execute |
| Packet Integrity | CRC valid, sequence ok, fresh | — | Packet *is* valid |
| Governance Authority | — | Revoked (epoch mismatch) | Command *must not* execute |

Both must be true for execution.

### 4. Measurable Enforcement

SLC enforcement is **measurable at the receiver**:

- **Authority revoked:** Receiver ingress has zero packets
- **Halos still permits:** Receiver logs show no connection failure
- **Packet is unchanged:** If captured, digest matches authority record
- **Governance state:** Epoch transition logged externally

**Consequence:** Evidence is concrete and auditable.

### 5. Upstream of Receiver Validation

The gate is positioned **before receiver validation**, so:

- Receiver is unaware of SLC enforcement
- SLC does not depend on receiver behavior
- Receiver validates packet independently (CRC, sequence, freshness, etc.)
- On ALLOW, receiver performs full Halos-level validation

**Consequence:** Defense in depth — SLC and Halos validate independently.

---

## Gate Implementation Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────┐
│ Halos SDM                                               │
│ - Decision: PERMISSIVE / RESTRICTIVE                    │
│ - Output: 64-byte ATL packet                            │
│   (opcode, sequence, timestamp, params, CRC)           │
└─────────┬───────────────────────────────────────────────┘
          │ original packet
          ↓
┌─────────────────────────────────────────────────────────┐
│ SLC Gate (Insertion Point)                              │
│                                                         │
│ Input:  packet (64 bytes)                              │
│         governance (context, epoch, permissions)        │
│         authority_db (digest -> grant record)            │
│                                                         │
│ Process:                                                │
│   1. Compute SHA-256(packet)                            │
│   2. Lookup authority_db[digest]                        │
│   3. Validate:                                          │
│      - packet size == 64                                │
│      - authority.epoch == governance.epoch              │
│      - authority.context == governance.context          │
│      - current_time <= authority.expiry                 │
│      - governance.route_permitted == true               │
│      - governance.safety_permitted == true              │
│   4. Decide: ALLOW or BLOCK                             │
│                                                         │
│ Output: packet (on ALLOW) or null (on BLOCK)            │
│         decision_code (reason for BLOCK, if applicable) │
└─────────┬───────────────────────────────────────────────┘
          │ (ALLOW: original packet)
          │ (BLOCK: nothing)
          ↓
┌─────────────────────────────────────────────────────────┐
│ UDP Transport                                           │
│ - Send packet to receiver (if available)                │
│ - UDP socket: 127.0.0.1:13000 (example)                │
└─────────┬───────────────────────────────────────────────┘
          │ packet (if sent)
          ↓
┌─────────────────────────────────────────────────────────┐
│ ATL Command Receiver                                    │
│ - UDP listen port                                       │
│ - Receive 64-byte packet (if SLC allows)               │
│ - Validate CRC, sequence, freshness (Halos-level)      │
│ - Parse opcode and dispatch                             │
└─────────────────────────────────────────────────────────┘
```

### Decision Logic (Pseudocode)

```python
def slc_gate_decide(packet: bytes, governance: Governance, 
                    authority_db: Dict, now_ms: int) -> (bool, str, bytes):
    """
    Core SLC gate decision logic.
    
    Returns:
      (allow: bool, reason: str, output_packet: bytes | None)
    """
    
    # Check 1: Packet size
    if len(packet) != 64:
        return (False, 'PACKET_SIZE_INVALID', None)
    
    # Check 2: Compute payload binding
    packet_digest = sha256(packet).hexdigest()
    
    # Check 3: Lookup authority
    if packet_digest not in authority_db:
        return (False, 'AUTHORITY_NOT_FOUND', None)
    
    authority = authority_db[packet_digest]
    
    # Check 4: Authority target match
    if authority.target != governance.target:
        return (False, 'TARGET_MISMATCH', None)
    
    # Check 5: Authority context match
    if authority.context_id != governance.context_id:
        return (False, 'CONTEXT_REVOKED', None)
    
    # Check 6: Authority time-to-live
    if now_ms > authority.valid_until_ms:
        return (False, 'AUTHORITY_EXPIRED', None)
    
    # Check 7: Epoch match (core authority enforcement)
    if authority.epoch != governance.epoch:
        return (False, 'EPOCH_MISMATCH', None)
    
    # Check 8: Route permission
    if not governance.route_permitted:
        return (False, 'ROUTE_REVOKED', None)
    
    # Check 9: Safety permission
    if not governance.safety_permitted:
        return (False, 'SAFETY_DENIED', None)
    
    # All checks passed
    return (True, 'COMMIT_AUTHORIZED', packet)
```

### Authority Record Structure

```python
@dataclass(frozen=True)
class Authority:
    packet_sha256: str            # SHA-256 digest of exact 64-byte packet
    context_id: str               # Governance context (e.g., 'ATL:FORKLIFT:01')
    epoch: int                    # Governance epoch (counter)
    target: str                   # Receiver target ('ATL_CMD_RECEIVER')
    valid_until_ms: int           # Time-to-live expiry (milliseconds)
    allow: bool = True            # Authority grant (True) or deny (False)
```

### Governance State Structure

```python
@dataclass(frozen=True)
class Governance:
    context_id: str               # Current governance context
    epoch: int                    # Current epoch (increments on authority change)
    target: str                   # Receiver target
    route_permitted: bool         # Route authorization (deployment permission)
    safety_permitted: bool        # Safety authorization (override capability)
```

---

## Integration Scenarios

### Scenario 1: Normal Execution (ALLOW)

**Initial State:**
- Governance: context='ATL:FORKLIFT:01', epoch=481, route=true, safety=true
- Authority: packet_sha256='abc123...', epoch=481, expiry=now+5000

**Event:**
- SDM emits valid CMD_UNMUTE packet (sha256='abc123...')
- SLC gate evaluates

**Decision Path:**
```
packet size == 64?                   ✓
digest == authority.packet_sha256?   ✓
target matches?                      ✓
context matches?                     ✓
epoch matches?                       ✓
not expired?                         ✓
route_permitted?                     ✓
safety_permitted?                    ✓

Result: ALLOW
Output: original packet forwarded
```

**Receiver Action:**
- Receives packet
- Validates CRC, sequence, freshness
- Parses CMD_UNMUTE
- Dispatches to safety function
- Motor enables

---

### Scenario 2: Authority Revoked (BLOCK via EPOCH_MISMATCH)

**Initial State:**
- Authority: packet_sha256='abc123...', epoch=481, expiry=now+5000
- Governance: epoch=481

**Trigger Event:**
- Operator revokes execution authority
- Governance epoch advances: 481 → 482

**SLC Gate Evaluates Same Packet:**
```
packet size == 64?                   ✓
digest == authority.packet_sha256?   ✓
target matches?                      ✓
context matches?                     ✓
epoch matches?                       ✗ (authority.epoch=481, governance.epoch=482)

Result: BLOCK
Reason: EPOCH_MISMATCH
Output: no packet forwarded
```

**Receiver State:**
- No packet received
- Motor remains in previous state
- No state change

**Evidence:**
- SDM packet was emitted (logs show it)
- Receiver ingress: zero packets
- SLC log: EPOCH_MISMATCH at timestamp T

---

### Scenario 3: Authority Expires (BLOCK via AUTHORITY_EXPIRED)

**Initial State:**
- Authority: expiry_ms = 1000000
- Current time: 1000005

**SLC Gate Evaluates:**
```
packet size == 64?                   ✓
digest == authority.packet_sha256?   ✓
target matches?                      ✓
context matches?                     ✓
epoch matches?                       ✓
not expired?                         ✗ (current_time > expiry_ms)

Result: BLOCK
Reason: AUTHORITY_EXPIRED
Output: no packet forwarded
```

**Recovery:**
- Authority is reissued with new expiry
- New packet is allowed

---

### Scenario 4: Governance Route Revoked (BLOCK via ROUTE_REVOKED)

**Initial State:**
- Authority: context='ATL:FORKLIFT:01', epoch=481
- Governance: context='ATL:FORKLIFT:01', epoch=481, route_permitted=false

**SLC Gate Evaluates:**
```
packet size == 64?                   ✓
digest == authority.packet_sha256?   ✓
target matches?                      ✓
context matches?                     ✓
epoch matches?                       ✓
not expired?                         ✓
route_permitted?                     ✗ (governance.route_permitted = false)

Result: BLOCK
Reason: ROUTE_REVOKED
Output: no packet forwarded
```

**Consequence:**
- Deployment route is administratively disabled
- No SLC-authorized commands can be forwarded until route is re-enabled

---

## Insertion Implementation Options

### Option 1: Proxy SDM (Recommended for PoC)

```c
// Wrapper around SDM emission
class SLCSDMProxy {
    private:
        SDM* real_sdm;
        SLCGate* gate;
    
    public:
        void emit_command(atl_cmd_pkt_t* pkt) {
            // Call original SDM to generate packet
            real_sdm->serialize_packet(pkt);
            
            // SLC gate decision
            Authority auth = ... // lookup or provision
            Governance gov = ... // get current state
            
            bool allow = gate->decide(pkt, auth, gov);
            
            if (allow) {
                // Forward original packet
                send_to_receiver(pkt);
            } else {
                // Drop packet (log reason)
                log_blocked_command(pkt, reason);
            }
        }
};
```

### Option 2: Socket Hook (Advanced)

```c
// Intercept UDP send at transport layer
int intercepted_sendto(int sock, const void* buf, size_t len,
                      int flags, const struct sockaddr* dest_addr,
                      socklen_t dest_len) {
    
    // Check if this is an ATL packet
    if (is_atl_packet(buf, len)) {
        // SLC gate decision
        if (!slc_gate_decide((uint8_t*)buf, len)) {
            // Drop packet by returning error
            return -1;  // EACCES
        }
    }
    
    // Call original sendto
    return real_sendto(sock, buf, len, flags, dest_addr, dest_len);
}
```

### Option 3: Receiver Pre-Filter (Alternative)

```c
// Insert SLC gate in receiver's ingress loop
class SLCReceiverFilter {
    private:
        ATLCommandReceiver* real_receiver;
        SLCGate* gate;
    
    public:
        atl_cmd_pkt_t* receive_packet() {
            atl_cmd_pkt_t* pkt = real_receiver->receive_packet();
            
            if (pkt != nullptr) {
                // SLC gate decision
                if (!gate->decide(pkt)) {
                    // Drop packet
                    log_rejected_command(pkt);
                    return nullptr;
                }
            }
            
            return pkt;
        }
};
```

**Rationale:** Option 1 (proxy) is cleanest for PoC because:
- No modification of SDM internals
- Clear insertion point
- Easy to instrument and measure
- Preserves original packet bytes exactly

---

## Decisive Experiment Design

### Experiment Goal

Prove that SLC provides **independent execution-authority enforcement** orthogonal to Halos safety decisions.

### Setup Phase

1. **Establish baseline:**
   ```
   Halos SDM: PERMISSIVE (ready to emit CMD_UNMUTE)
   Authority DB: contains entry for this packet
   Governance: epoch=481, route_permitted=true
   Receiver: listening on :13000, packet count=0
   ```

2. **Issue authority:**
   ```
   Authority {
     packet_sha256: SHA-256(exact_CMD_UNMUTE_bytes),
     context: 'ATL:FORKLIFT:01',
     epoch: 481,
     expiry: now + 5000
   }
   ```

3. **Emit packet (T0):**
   ```
   SDM emits CMD_UNMUTE → SLC gate decides ALLOW → forwarded to receiver
   Receiver counts: 1 packet
   Motor state: ENABLED
   ```

### Trigger Phase

4. **Revoke authority (T1):**
   ```
   Governance epoch advances: 481 → 482
   Authority DB unchanged (old entry still at epoch=481)
   ```

5. **Replay packet (T2):**
   ```
   Same exact packet bytes are replayed/sent again
   SLC gate decision:
     - digest matches: ✓
     - epoch mismatch: ✗ (auth.epoch=481, gov.epoch=482)
     - Result: BLOCK
   Packet NOT forwarded
   ```

### Verification Phase

6. **Measure outcomes:**
   ```
   Halos safety state: still PERMISSIVE (SDM would emit same packet again)
   Packet integrity: unchanged (CRC still valid)
   Receiver packet count: UNCHANGED (no new packets received)
   SLC log: EPOCH_MISMATCH at T2
   Reason: Authority for this packet is stale after epoch advance
   ```

### Evidence Matrix

| Metric | Expected | Actual | Pass? |
|--------|----------|--------|-------|
| Halos decision at T1 | PERMISSIVE | — | — |
| Halos decision at T2 | PERMISSIVE | — | — |
| Packet bytes at T0 | identical to T2 | — | — |
| Packet CRC at T0 | valid | — | — |
| Packet CRC at T2 | valid | — | — |
| Receiver count at T0 | 1 | — | — |
| Receiver count at T2 | 1 (no new packets) | — | — |
| SLC decision at T2 | BLOCK | — | — |
| SLC reason at T2 | EPOCH_MISMATCH | — | — |

### Conclusion Criteria

**SLC enforcement is proven independent if:**
- ✓ Halos remains permissive (safety decision unchanged)
- ✓ Packet bytes are identical (no modification)
- ✓ Packet CRC is valid (integrity preserved)
- ✓ Receiver ingress is blocked (SLC gate action)
- ✓ SLC log shows EPOCH_MISMATCH (authority revocation)

---

## Deployment Configuration

### SLC Gate Configuration (Example YAML)

```yaml
slc_gate:
  enabled: true
  mode: "packet_preserving"
  
  insert_point:
    location: "sdm_to_receiver"
    protocol: "atl_cmd_pkt"
    packet_size: 64
    binding_method: "sha256"
  
  authority_db:
    backend: "file"  # or "redis", "postgres"
    path: "/var/lib/slc/authority.db"
    gc_policy: "ttl"
  
  governance:
    context: "ATL:FORKLIFT:01"
    epoch_source: "external"  # governance system manages epoch
    audit_log: "/var/log/slc/decisions.log"
  
  transport:
    listen_addr: "127.0.0.1"
    listen_port: 12000
    forward_addr: "127.0.0.1"
    forward_port: 13000
    timeout_ms: 100
  
  decision_codes:
    ALLOW:
      - "COMMIT_AUTHORIZED"
    BLOCK:
      - "EPOCH_MISMATCH"
      - "AUTHORITY_EXPIRED"
      - "CONTEXT_REVOKED"
      - "ROUTE_REVOKED"
      - "SAFETY_DENIED"
      - "PAYLOAD_BINDING_FAIL"
      - "PACKET_SIZE"
```

### Governance State Update (Example)

```python
# External governance system revokes authority
def revoke_authority(context_id: str):
    governance[context_id].epoch += 1
    governance[context_id].route_permitted = False
    log_governance_change(context_id, "ROUTE_REVOKED")

# Result: All existing authority records (with old epoch) become invalid
revoke_authority("ATL:FORKLIFT:01")
```

---

## Verification Checklist

- [ ] Gate implementation preserves all 64 bytes on ALLOW
- [ ] Gate implementation produces zero bytes on BLOCK
- [ ] Authority binding uses SHA-256(full_packet)
- [ ] Epoch mismatch is correctly detected
- [ ] SLC logs include decision reason and timestamp
- [ ] Receiver ingress can be measured (packet count or tcpdump)
- [ ] Halos safety logic is unmodified
- [ ] No CRC/sequence/freshness modifications
- [ ] Governance state machine correctly advances epoch
- [ ] Authority records are correctly provisioned
- [ ] TTL/expiry handling is correct
- [ ] Error conditions are logged

