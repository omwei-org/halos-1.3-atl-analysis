from __future__ import annotations

import base64
import json
import time
import urllib.request


BASE = "http://127.0.0.1:8080"


def post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def main() -> None:
    authorization = post("/authorize", {"env_id": 0})
    epoch = int(authorization["authority_epoch"])
    print(json.dumps({"event": "AUTHORIZED", "epoch": epoch}))

    # Simulated autonomous controller: it keeps producing commands even after
    # execution authority is revoked. The Magic Box decides whether they commit.
    commands = [b"RELAY:ON", b"RELAY:OFF", b"RELAY:ON", b"RELAY:OFF"]
    for index, payload in enumerate(commands):
        if index == 2:
            post("/revoke", {"env_id": 0})
            print(json.dumps({"event": "AUTHORITY_REVOKED"}))

        result = post(
            "/execute",
            {
                "env_id": 0,
                "execution_epoch": epoch,
                "payload_b64": base64.b64encode(payload).decode("ascii"),
                "safety": "ALLOW",
            },
        )
        print(json.dumps({"event": "CONTROLLER_COMMAND", "payload": payload.decode(), "result": result}))
        time.sleep(0.5)


if __name__ == "__main__":
    main()
