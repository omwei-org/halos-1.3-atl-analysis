from __future__ import annotations

import base64
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from poc.commit_gate import SafetyDecision
from poc.gie import GIE
from poc.physical_boundary import GovernedPhysicalPath, PhysicalExecutionObject, RecordingRelay
from runtime.host_io_client import HostIOClient


class RuntimeRelay:
    """In-memory reference actuator used when no external host I/O is configured."""

    def __init__(self) -> None:
        self._relay = RecordingRelay()

    def apply(self, payload: bytes) -> None:
        self._relay.apply(payload)
        print(json.dumps({"event": "ACTUATOR_APPLY", "payload_b64": base64.b64encode(payload).decode()}), flush=True)

    @property
    def state(self) -> bool:
        return self._relay.state


class MagicBox:
    """Long-running hardware-agnostic runtime around the invariant-driven core."""

    def __init__(self, actuator: object | None = None) -> None:
        self.gie = GIE()
        if actuator is None:
            socket_path = os.getenv("MAGIC_BOX_IO_SOCKET")
            actuator = HostIOClient(socket_path) if socket_path else RuntimeRelay()
        self.actuator = actuator
        self.path = GovernedPhysicalPath(self.gie, env_id=0, actuator=self.actuator)

    def authorize(self, env_id: int = 0) -> int:
        return self.gie.grant(env_id)

    def revoke(self, env_id: int = 0) -> None:
        self.gie.revoke(env_id)

    def execute(self, payload: bytes, execution_epoch: int, safety: SafetyDecision = SafetyDecision.ALLOW,
                safety_reason: str = "halos_safe", env_id: int = 0) -> dict[str, Any]:
        execution = PhysicalExecutionObject(env_id=env_id, payload=payload, execution_epoch=execution_epoch)
        result = self.path.commit(execution, safety, safety_reason)
        relay_state = getattr(self.actuator, "state", None)
        return {
            "decision": result.decision.value,
            "reason": result.reason,
            "action_digest": result.action_digest,
            "execution_epoch": result.execution_epoch,
            "applied": result.applied,
            "relay_state": relay_state,
        }


BOX = MagicBox()


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"status": "ok", "runtime": "equinibrium-magic-box"})
            return
        if self.path == "/state":
            self._json(200, {"status": "ok", "authority_epoch": BOX.gie.current_epoch(0), "relay_state": getattr(BOX.actuator, "state", None)})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/authorize":
                epoch = BOX.authorize(int(body.get("env_id", 0)))
                self._json(200, {"decision": "ALLOW", "authority_epoch": epoch})
                return
            if self.path == "/revoke":
                BOX.revoke(int(body.get("env_id", 0)))
                self._json(200, {"decision": "BLOCK", "reason": "revoked"})
                return
            if self.path == "/execute":
                payload = base64.b64decode(body["payload_b64"], validate=True)
                safety = SafetyDecision(body.get("safety", SafetyDecision.ALLOW.value))
                result = BOX.execute(payload=payload, execution_epoch=int(body["execution_epoch"]),
                                     safety=safety, safety_reason=str(body.get("safety_reason", "halos_safe")),
                                     env_id=int(body.get("env_id", 0)))
                self._json(200, result)
                return
            self._json(404, {"error": "not_found"})
        except (KeyError, ValueError, TypeError, base64.binascii.Error, json.JSONDecodeError, OSError, RuntimeError) as exc:
            self._json(400, {"error": "invalid_request", "detail": str(exc)})

    def log_message(self, format: str, *args: object) -> None:
        print(format % args, flush=True)


def main() -> None:
    host = os.getenv("MAGIC_BOX_HOST", "0.0.0.0")
    port = int(os.getenv("MAGIC_BOX_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(json.dumps({"event": "MAGIC_BOX_READY", "host": host, "port": port}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
