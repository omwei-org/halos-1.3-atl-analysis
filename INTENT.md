# Intent — HALOS Revocation and Protected-Effect Evidence

## Why this work exists

Establish evidence that authority revocation and recovery semantics are enforced at the point where a Protected Effect can actually occur—not merely at enqueue time, authorization-check time, or API return time.

The unit of security analysis is the **actual Protected Effect**. A queued operation, accepted request, successful function return, local status record, or transport acknowledgement is not by itself proof that the effect did or did not happen.

## Questions this work must answer

1. Can a prepared or queued operation cause a Protected Effect after its governing authority has been revoked?
2. Does the guarded path reject stale authority at the actual commit boundary?
3. Does an unguarded negative control demonstrably produce the unsafe effect, so the test can detect a broken guard?
4. If the downstream effect occurs but the process crashes before recording the outcome, does recovery represent the outcome as unknown and reconcile it before retry?
5. Can the number of actual effects be measured independently of call results and local bookkeeping, including detection of duplicates?

## Current test scope

- **T1 — queued → revoke → release:** guarded path must produce zero downstream effects.
- **T2 — unguarded negative control:** the deliberately unguarded path must produce a real simulated downstream effect after revocation, visibly exposing the unsafe behavior.
- **T3 — crash after effect, before result recording:** downstream effect exists while the local outcome is unknown.
- **T4 — reconciliation before retry:** recovery checks authoritative downstream state before retry; an already-applied effect must not be repeated.
- **T5 — independent effect accounting:** count effects at a separate downstream observer/sink, not from return values, local status, or queue bookkeeping.

## Evidence discipline

Keep these categories distinct in every report:

- **Demonstrated:** directly exercised and measured by the test.
- **Simulated:** modeled in software, without claiming physical or external-system validation.
- **Unverified:** depends on real actuator/transport properties, durable storage, authoritative effect lookup, or deployment assumptions not established by this PoC.

A passing CI run proves that the checked tests passed. It does not, by itself, prove the security invariant in a real deployment.

## Engineering constraints

- Extend the existing PoC and preserve useful prior tests; do not create a parallel test project.
- Exercise a real simulated downstream effect; never use a no-op callback as evidence of an in-flight effect.
- Use deterministic synchronization for concurrency tests.
- Serialize revocation and final commit validation/effect where the design requires an atomic boundary.
- Treat an ambiguous post-crash outcome as **UNKNOWN** until reconciled.
- Do not retry an unknown operation until downstream state has been checked.
- Do not assume an idempotency key provides exactly-once behavior unless its actual semantics are tested.
- Keep changes on the working branch and do not merge without explicit authorization.

## Current execution context

- Repository: `omwei-org/halos-1.3-atl-analysis`
- Working branch: `work/protected-effect-revocation-recovery`
- Current work is tracked in draft PR #3: revocation at the effect boundary plus crash/reconciliation tests.
- PR #2 (`eabc-effect-correlation-004`) is separate work concerning commit-to-observed-effect correlation; do not silently merge its scope into this task.

## Completion condition

Do not call this work complete until T1–T5 have been run, their actual effect counts and outcomes reported, relevant CI has completed, and all remaining simulation/deployment limitations are explicit.

Do not report success to external parties (including LinkedIn) before the corresponding evidence exists.
