from __future__ import annotations

import os
import tempfile
import threading
import time

from poc.commit_gate import SafetyDecision
from runtime.host_io import RelayHostAdapter, RelayOutput
from runtime.host_io_client import HostIOClient
from runtime.magic_box import MagicBox


def test_magic_box_reaches_host_io_only_after_commit() -> None:
    with tempfile.TemporaryDirectory() as directory:
        socket_path = os.path.join(directory, "io.sock")
        output = RelayOutput()
        adapter = RelayHostAdapter(socket_path, output)
        thread = threading.Thread(target=adapter.serve_forever, daemon=True)
        thread.start()

        deadline = time.monotonic() + 2.0
        while not os.path.exists(socket_path):
            assert time.monotonic() < deadline
            time.sleep(0.01)

        box = MagicBox(actuator=HostIOClient(socket_path))
        epoch = box.authorize(0)

        allowed = box.execute(b"RELAY:ON", epoch, SafetyDecision.ALLOW)
        assert allowed["decision"] == "ALLOW"
        assert allowed["applied"] is True
        assert output.value is True
        assert output.transitions == [True]

        box.revoke(0)
        blocked = box.execute(b"RELAY:OFF", epoch, SafetyDecision.ALLOW)
        assert blocked["decision"] == "BLOCK"
        assert blocked["applied"] is False
        assert output.value is True
        assert output.transitions == [True]
