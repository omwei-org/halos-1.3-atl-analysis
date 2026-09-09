from __future__ import annotations

import base64
import json
import socket
import threading

from runtime.adapters.unix_socket_actuator import UnixSocketActuator


def _server(path: str, received: list[bytes], ready: threading.Event) -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(path)
        server.listen(1)
        ready.set()
        connection, _ = server.accept()
        with connection:
            request = json.loads(connection.makefile("rb").readline())
            payload = base64.b64decode(request["payload_b64"], validate=True)
            received.append(payload)
            response = {
                "applied": True,
                "payload_b64": base64.b64encode(payload).decode("ascii"),
            }
            connection.sendall((json.dumps(response) + "\n").encode("utf-8"))


def test_unix_socket_actuator_preserves_exact_payload(tmp_path) -> None:
    path = str(tmp_path / "magic-box-io.sock")
    received: list[bytes] = []
    ready = threading.Event()
    thread = threading.Thread(target=_server, args=(path, received, ready), daemon=True)
    thread.start()
    ready.wait(timeout=1)

    actuator = UnixSocketActuator(path)
    payload = b"RELAY:ON"
    actuator.apply(payload)
    thread.join(timeout=1)

    assert received == [payload]
