from __future__ import annotations

from typing import Protocol


class DigitalOutput(Protocol):
    def set(self, value: bool) -> None: ...


class GPIORelayAdapter:
    """Thin GPIO adapter; governance remains completely hardware-agnostic.

    The adapter intentionally accepts only the already-approved opaque
    payload. Protocol decoding belongs at this physical-I/O edge.
    """

    def __init__(self, output: DigitalOutput) -> None:
        self._output = output

    def apply(self, payload: bytes) -> None:
        if payload == b"RELAY:ON":
            self._output.set(True)
            return
        if payload == b"RELAY:OFF":
            self._output.set(False)
            return
        raise ValueError("unsupported relay payload")


class RecordingDigitalOutput:
    """Deterministic GPIO substitute for host-independent integration tests."""

    def __init__(self) -> None:
        self.value = False
        self.transitions: list[bool] = []

    def set(self, value: bool) -> None:
        self.value = value
        self.transitions.append(value)
