from dataclasses import dataclass
from hashlib import sha256
from typing import Optional

@dataclass(frozen=True)
class Authority:
    packet_sha256: str
    context_id: str
    epoch: int
    target: str
    valid_until_ms: int

@dataclass(frozen=True)
class Governance:
    context_id: str
    epoch: int
    target: str
    route_permitted: bool
    safety_permitted: bool

@dataclass(frozen=True)
class GateResult:
    allow: bool
    code: str
    packet: Optional[bytes]

class SLCHalosAdapter:
    """Packet-preserving software model of an SLC boundary adapter.

    The adapter does not reinterpret or rewrite the Halos ATL packet. It hashes
    the exact bytes and binds authority to that digest plus governance context.
    """
    def issue_authority(self, packet: bytes, gov: Governance, now_ms: int,
                        ttl_ms: int = 1000) -> Authority:
        if len(packet) != 64:
            raise ValueError('ATL packet must be exactly 64 bytes in this PoC')
        return Authority(
            sha256(packet).hexdigest(), gov.context_id, gov.epoch,
            gov.target, now_ms + ttl_ms
        )

    def commit(self, packet: bytes, authority: Authority,
               gov: Governance, now_ms: int) -> GateResult:
        if len(packet) != 64:
            return GateResult(False, 'PACKET_SIZE', None)
        digest = sha256(packet).hexdigest()
        if digest != authority.packet_sha256:
            return GateResult(False, 'PAYLOAD_BINDING_FAIL', None)
        if now_ms > authority.valid_until_ms:
            return GateResult(False, 'AUTHORITY_EXPIRED', None)
        if gov.context_id != authority.context_id:
            return GateResult(False, 'CONTEXT_REVOKED', None)
        if gov.epoch != authority.epoch:
            return GateResult(False, 'EPOCH_MISMATCH', None)
        if gov.target != authority.target:
            return GateResult(False, 'TARGET_MISMATCH', None)
        if not gov.route_permitted:
            return GateResult(False, 'ROUTE_REVOKED', None)
        if not gov.safety_permitted:
            return GateResult(False, 'SAFETY_DENIED', None)
        # Critical property: exact packet is returned unchanged.
        return GateResult(True, 'COMMIT_AUTHORIZED', packet)
