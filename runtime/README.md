# Equinibrium Magic Box Runtime

The runtime is the deployable host/container layer around the invariant-driven execution boundary.

## Contract

```text
Autonomous controller
        |
        | opaque execution payload
        v
   HTTP /execute
        |
        v
+-----------------------+
| Equinibrium Magic Box |
| GIE                   |
| Safety                |
| Identity              |
| Freshness             |
| Commit Gate           |
+-----------+-----------+
            |
            | only after ALLOW
            v
      Actuator Adapter
            |
            v
         Relay
```

The CPU, Linux distribution, container runtime and physical I/O technology are deployment details. The governance core has no Raspberry Pi dependency.

## API

`GET /health` — liveness.

`GET /state` — current authority epoch and relay state.

`POST /authorize`

```json
{"env_id": 0}
```

Returns the newly issued authority epoch.

`POST /revoke`

```json
{"env_id": 0}
```

Revokes the current authority. Previously stamped execution objects remain stale and are blocked.

`POST /execute`

```json
{
  "env_id": 0,
  "execution_epoch": 1,
  "payload_b64": "UkVMQVk6T04=",
  "safety": "ALLOW"
}
```

The runtime hashes the exact payload and sends it through the existing GIE → Safety → Commit Gate composition. The actuator adapter is called only after ALLOW.

## Run on any Linux host

```bash
docker compose -f runtime/docker-compose.yml up --build
```

For the first physical demo, replace `RuntimeRelay` with a host-specific GPIO relay adapter. Do not put GPIO assumptions into GIE, Commit Gate, or the execution identity layer.

## PoC boundary

This container is a reference runtime, not a trusted hardware security boundary. The physical host can still compromise the software process. The purpose of this stage is to demonstrate that the same execution invariants can sit inline between an unchanged autonomous controller and a physical effect.
