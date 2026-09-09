from __future__ import annotations

import base64
import json
import os
import socket
from dataclasses import dataclass

from runtime.commit_envelope import CommittedEnvelope


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
    """Host-side physical-I/O adapter for the committed-envelope boundary.

    The adapter performs only structural envelope validation and a 1:1 mapping
    from target/state to the physical relay output. It does not recompute or
    verify action_digest and does not make governance decisions.
    """

    def __init__(self, socket_path: str, output: RelayOutput | None = None) -> None:
        self.socket_path = socket_path
        self.output = output or RelayOutput()

    def apply(self, envelope_bytes: bytes) -> None:
        envelope = CommittedEnvelope.from_dict(json.loads(envelope_bytes.decode("utf-8")))
        if envelope.target != "RELAY_1":
            raise ValueError("unsupported relay target")
        if envelope.state == "ON":
            self.output.set(True)
            return
        if envelope.state == "OFF":
            self.output.set(False)
            return
        raise ValueError("unsupported relay state")

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
                    envelope_bytes = base64.b64decode(json.loads(data)["payload_b64"], validate=True)
                    self.apply(envelope_bytes)
                    response = {
                        "applied": True,
                        "payload_b64": base64.b64encode(envelope_bytes).decode("ascii"),
                    }
                    connection.sendall((json.dumps(response) + "\n").encode("utf-8"))


def main() -> None:
    path = os.getenv("MAGIC_BOX_IO_SOCKET", "/run/equinibrium/magic-box-io.sock")
    RelayHostAdapter(path).serve_forever()


if __name__ == "__main__":
    main()
