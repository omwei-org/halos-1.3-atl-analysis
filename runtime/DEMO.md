# Magic Box live demo

This demo shows the key retrofit property: the autonomous controller keeps generating and submitting commands after authority is revoked, while the physical actuator stops changing.

## Start

```bash
docker compose -f runtime/docker-compose.yml up --build
```

In another terminal:

```bash
python runtime/demo_controller.py
```

## Expected sequence

1. The controller receives an authority epoch.
2. Commands before revocation are committed and reach the actuator.
3. The controller continues generating commands.
4. `/revoke` invalidates the authority epoch.
5. Subsequent commands are still accepted by the runtime API, but the Commit Gate returns `BLOCK` and `applied=false`.
6. No physical adapter call occurs after the block.

The demo therefore distinguishes **continued inference / command generation** from **physical execution authority**.

## What this proves

At runtime level, the PoC demonstrates:

`controller continues → governance blocks → physical effect does not occur`

This is the concrete runtime manifestation of invariant I-32. It does not claim that Docker, Linux, or the reference host provides a trusted hardware security boundary.
