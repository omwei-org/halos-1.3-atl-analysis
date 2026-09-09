from __future__ import annotations

import base64
import json
import socket


class HostIOClient:
    """Magic Box-side client for the untrusted/platform-specific host I/O process."""

    def __init__(self, socket_path: str) -> None:
        self.socket_path = socket_path

    def apply(self, payload: bytes) -> None:
        request = json.dumps({"payload_b64": base64.b64encode(payload).decode("ascii")}) + "\n"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2.0)
            connection.connect(self.socket_path)
            connection.sendall(request.encode("utf-8"))
            response = json.loads(connection.makefile("rb").readline())
        if response.get("applied") is not True:
            raise RuntimeError("host I/O adapter rejected committed envelope")


if __name__ == "__main__":
    raise SystemExit("HostIOClient is a library adapter; start runtime.host_io for the host process.")
