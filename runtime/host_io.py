from __future__ import annotations

import base64
import json
import os
import socket
from dataclasses import dataclass


@dataclass
class RelayOutput:
    value: bool = False
    transitions: list[bool] | None = None

    def __post_init__(self) -> None:
        if self.transitions is None:
            self.transitions = []

    def set(self, value: bool) -> None:
        self.value = value
        self.transitions.append(value)


class RelayHostAdapter:
    """Host-side physical-I/O adapter.

    This process is deliberately outside the governance core. It receives only
    payloads that the Magic Box has already committed and translates the opaque
    payload at the physical-I/O edge.
    """

    def __init__(self, socket_path: str, output: RelayOutput | None = None) -> None:
        self.socket_path = socket_path
        self.output = output or RelayOutput()

    def apply(self, payload: bytes) -> None:
        if payload == b"RELAY:ON":
            self.output.set(True)
            return
        if payload == b"RELAY:OFF":
            self.output.set(False)
            return
        raise ValueError("unsupported relay payload")

    def serve_forever(self) -> None:
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(self.socket_path)
            os.chmod(self.socket_path, 0o660)
            server.listen(8)
            print(json.dumps({"event": "HOST_IO_READY", "socket": self.socket_path}), flush=True)
            while True:
                connection, _ = server.accept()
                with connection:
                    data = connection.makefile("rb").readline()
                    request = json.loads(data)
                    payload = base64.b64decode(request["payload_b64"], validate=True)
                    self.apply(payload)
                    response = {"applied": True, "payload_b64": base64.b64encode(payload).decode("ascii")}
                    connection.sendall((json.dumps(response) + "\n").encode("utf-8"))


def main() -> None:
    path = os.getenv("MAGIC_BOX_IO_SOCKET", "/run/equinibrium/magic-box-io.sock")
    RelayHostAdapter(path).serve_forever()


if __name__ == "__main__":
    main()
