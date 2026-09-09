from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol, TypeVar


class ExecutionObject(Protocol):
    """Protocol for concrete objects that may cross an execution boundary."""

    def canonical_bytes(self) -> bytes: ...


T = TypeVar("T", bound=ExecutionObject)


@dataclass(frozen=True)
class ExecutionIdentity:
    """Stable identity of one concrete execution object."""

    digest: str
    execution_epoch: int


def digest_bytes(payload: bytes) -> str:
    """Hash the exact canonical execution bytes without reinterpretation."""
    return sha256(payload).hexdigest()


def identify(obj: ExecutionObject, execution_epoch: int) -> ExecutionIdentity:
    """Create non-authoritative identity for a concrete execution object."""
    return ExecutionIdentity(digest_bytes(obj.canonical_bytes()), execution_epoch)


@dataclass(frozen=True)
class BytesExecutionObject:
    """Generic execution object for byte-oriented downstream boundaries."""

    payload: bytes

    def canonical_bytes(self) -> bytes:
        return self.payload
