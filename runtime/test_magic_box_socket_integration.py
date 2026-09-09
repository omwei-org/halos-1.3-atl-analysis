from __future__ import annotations

import base64
import json
import socket
import threading

from poc.commit_gate import SafetyDecision
from runtime.magic_box import MagicBox
from runtime.adapters.unix_socket_actuator import UnixSocketActuator


class RecordingHost:
    def __init__(self, path: str) -> None:
        self.path = path
        self.received: list[bytes] = []
        self.thread = threading.Thread(target=self.serve_once, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def join(self) -> None:
        self.thread.join(timeout=1)

    def serve_once(self) -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(self.path)
            server.listen(8)
            while len(self.received) < 1:
                connection, _ = server.accept()
                with connection:
                    request = json.loads(connection.makefile("rb").readline())
                    payload = base64.b64decode(request["payload_b64"], validate=True)
                    self.received.append(payload)
                    response = {
                        "applied": True,
                        "payload_b64": base64.b64encode(payload).decode("ascii"),
                    }
                    connection.sendall((json.dumps(response) + "\n").encode("utf-8"))


def test_magic_box_allow_crosses_socket_to_host(tmp_path) -> None:
    path = str(tmp_path / "magic-box-io.sock")
    host = RecordingHost(path)
    host.start()

    box = MagicBox(actuator=UnixSocketActuator(path))
    epoch = box.authorize(0)
    result = box.execute(b"RELAY:ON", epoch, SafetyDecision.ALLOW)
    host.join()

    assert result["decision"] == "ALLOW"
    assert result["applied"] is True
    assert host.received == [b"RELAY:ON"]


def test_magic_box_block_does_not_cross_socket(tmp_path) -> None:
    path = str(tmp_path / "magic-box-io.sock")
    box = MagicBox(actuator=UnixSocketActuator(path))
    epoch = box.authorize(0)
    box.revoke(0)

    result = box.execute(b"RELAY:OFF", epoch, SafetyDecision.ALLOW)

    assert result["decision"] == "BLOCK"
    assert result["applied"] is False
    assert result["reason"] in {"authority_block", "execution_epoch_mismatch"}
