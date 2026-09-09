from __future__ import annotations

import base64
import json
import socket


class UnixSocketActuator:
    """Magic Box actuator that forwards an already-committed payload to host I/O.

    The transport carries only an opaque payload. It makes no allow/deny
    decision of its own; the decision was already final before apply() is
    called, and this adapter forwards the resulting bytes byte-for-byte.
    """

    def __init__(self, socket_path: str, timeout: float = 2.0) -> None:
        self.socket_path = socket_path
        self.timeout = timeout

    def apply(self, payload: bytes) -> None:
        request = json.dumps(
            {"payload_b64": base64.b64encode(payload).decode("ascii")}
        ) + "\n"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout)
            connection.connect(self.socket_path)
            connection.sendall(request.encode("utf-8"))
            response = json.loads(connection.makefile("rb").readline())

        if response.get("applied") is not True:
            raise RuntimeError("host I/O adapter rejected committed payload")

        returned = base64.b64decode(response["payload_b64"], validate=True)
        if returned != payload:
            raise RuntimeError("host I/O adapter returned a mutated payload")
