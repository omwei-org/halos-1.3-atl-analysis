# Equinibrium Magic Box PoC

## Purpose

The next PoC step is a **hardware-agnostic inline execution boundary** between an unchanged autonomous controller and a physical actuator.

The host CPU and physical I/O are deployment substrates. They are not the security claim.

> The host provides compute and I/O. Equinibrium provides the execution-governance boundary.

## Reference topology

```text
 AUTONOMOUS CONTROLLER
         |
         | command
         v
 +---------------------------+
 |   EQUINIBRIUM MAGIC BOX   |
 |                           |
 | GIE                       |
 | Safety Adapter            |
 | Execution Identity        |
 | Freshness / Epoch         |
 | Commit Gate               |
 |                           |
 |     GOVERNANCE DOMAIN     |
 +-------------+-------------+
               |
          Adapter API
               |
 +-------------v-------------+
 | HOST / I-O SUBSTRATE      |
 | GPIO / Serial / CAN / USB |
 | TCP / UDP / MQTT / ...    |
 +-------------+-------------+
               |
             RELAY
               |
               v
          PHYSICAL LOAD
```

## Host neutrality

The same governance runtime should be deployable on:

- Raspberry Pi or another ARM SBC
- x86 mini-PC / industrial PC
- NVIDIA Jetson
- embedded Linux gateway
- VM or container host
- any other platform providing CPU and the required I/O adapter

Raspberry Pi is therefore a **reference host**, not part of the architecture.

## Core contract

The governance core sees an opaque execution object:

```text
ExecutionObject = environment + exact payload + execution epoch
```

The core does not need to know whether the payload ultimately drives a relay, servo, CAN actuator, robot controller, or another physical interface.

The physical adapter is invoked only after:

```text
Authority AND Safety AND Identity AND Freshness
                         |
                         v
                PHYSICAL COMMIT
```

## Critical boundary property

There is exactly one transition from the governance domain to physical I/O:

```text
Commit Gate ALLOW -> actuator.apply(payload)
Commit Gate BLOCK  -> no actuator call
```

A BLOCK must therefore be observable as a **zero physical effect**, while upstream autonomous inference may continue.

## First physical demonstration

Use a simple relay as the first actuator. A relay is intentionally boring: it makes the execution boundary visible without introducing robot-specific semantics.

Example:

```text
Controller emits: RELAY:ON
        |
        v
Magic Box checks authority/safety/identity/freshness
        |
      ALLOW
        |
        v
Relay energizes
```

Then revoke authority while the controller continues producing commands:

```text
Controller:  ON -> ON -> ON -> ON -> ...
                    |
                  REVOKE
                    |
Magic Box:  ALLOW -> BLOCK -> BLOCK -> BLOCK -> ...
                    |
Relay:       ON   -> unchanged / safe state
```

This demonstrates that execution authority is independent of continued inference.

## Integrity demonstration

Bind authority to the exact payload digest:

```text
Authorized payload: RELAY:ON
Mutated payload:    RELAY:OFF

same environment
same epoch
different digest
        |
        v
      BLOCK
```

The mutation is not allowed to inherit authorization merely because it arrived through the same controller or epoch.

## Adapter rule

Adapters may translate between the generic execution object and a physical protocol, but the governance core must not become protocol-specific.

Examples of future adapters:

```text
GPIOAdapter
SerialAdapter
CANAdapter
USBAdapter
TCPAdapter
UDPAdapter
MQTTAdapter
ROS2Adapter
```

For the first PoC, `RecordingRelay` is a deterministic software model of the physical adapter. The next deployment can replace it with a GPIO relay adapter without changing GIE, Commit Gate, execution identity, or the invariant contract.

## Deployment model

Containerization is preferred for the host-neutral PoC:

```text
+------------------------------+
| Linux host                   |
|                              |
| +--------------------------+ |
| | Equinibrium runtime      | |
| | GIE / Gate / adapters    | |
| +------------+-------------+ |
|              |              |
|        host I/O interface  |
+--------------+--------------+
               |
             relay
```

The container is a portability mechanism, not a trust boundary. The PoC must not claim that Docker, Linux, or the Raspberry Pi provides hardware-enforced protection.

## Scope discipline

This PoC deliberately does **not** move to RTL or claim physical hardware atomicity.

The software PoC demonstrates the invariant contract at the physical-effect boundary. Production Equinibrium can later move the same contract into a trusted hardware execution boundary.

## Success criterion

The strongest demo is:

```text
Existing controller
       |
       v
[ Equinibrium Magic Box ]
       |
       v
Existing actuator
```

with **no modification to the autonomous controller**.

That is the retrofit story:

> Put Equinibrium between the decision and the effect.
