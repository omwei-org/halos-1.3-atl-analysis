# Validation Run 002 — S3 baseline and S5 negative case

Both captures ran against `omwei-org/halos-1.3-atl-analysis@b3050fd2b3eb034f293333008257d989abe959b7`
under contract `omwei-org/omwei-eabc@c0debd85`, on one host, 2026-09-23.

| Directory | Controller commit | Scenarios executed |
|---|---|---|
| `s3-baseline/` | `ronrey/comos-federation@9647a2a7b9ea590652e81a22d19fd53b8751cac4` | S1, S3 |
| `s5-negative/` | `ronrey/comos-federation@4076fc5e52720016bed2cce4196714b8db2e4dfc` | S1, S3, S5 |

`s5-negative/` is one continuous session, one box process, one evidence file,
so its S3 is the same-session baseline for its S5. `s3-baseline/` is the
earlier standalone run, kept for comparison. S2 and S4 are declared in both
packages (NOT_CONSTRUCTIBLE, NOT_SUPPORTED_NOT_OBSERVABLE), not executed.

## Files

Each directory holds:

- `authority-side-b3050fd2.jsonl` — your `CommitEvidence` records, byte-for-byte
  as your `EvidenceRecorder` wrote them. Nothing reformatted.
- `controller-side-<commit>.json` — our evidence package in the §9 shape of your
  run-002 plan, including the exact payload bytes and the `evidence_ref` hash
  for every controller entry.
- `reconcile-output.shipped.txt` — output of our shipped `reconcile()`
  (TypeScript) on that pair.
- `reproduce-output.expected.txt` — what `reproduce.py` prints on that pair.

`SHA256SUMS` covers every data file and the script.

## Reproducing

Python 3.8+, standard library only, imports nothing from either codebase:

```
shasum -a 256 -c SHA256SUMS
python3 reproduce.py s5-negative/authority-side-b3050fd2.jsonl s5-negative/controller-side-4076fc5e.json
python3 reproduce.py s3-baseline/authority-side-b3050fd2.jsonl s3-baseline/controller-side-9647a2a7.json
```

For each pair it:

1. recomputes your chain from `_HASH_FIELD_ORDER`: `record_hash = sha256(prev_hash + concat(json.dumps(field, separators=(",", ":"))))`, genesis 64 zeroes
2. recomputes our chain from our recipe: `entry_hash = sha256(JSON array [seq, command_id, env_id, epoch, payload_digest, decision, reason or "", at, prev_hash])`, compact, UTF-8, genesis 64 zeroes. Every input is in the package; each result is compared against the `entry_hash` the package declares
3. pairs records by `command_id` alone, taking your EXECUTION record as the terminal one where it exists and COMMIT otherwise
4. applies our reconcile rules

Exit code is 0 only if both chains verify. If either fails, every verdict is
printed as UNTRUSTED.

Step 4 is a port. The authoritative reconciler is our TypeScript, which is in a
private repository, so the port is here to let you rerun the rules without it.
Its verdicts were diffed against the shipped function's output on both pairs
and are identical; the shipped output sits next to each capture so you can
make the same comparison yourself.

## Expected result

```
s5-negative/
S1_TOCTOU                    BLOCK ... stage=COMMIT    => MATCH_REFUSED
S3_BASELINE                  ALLOW ... stage=EXECUTION => MATCH
S5_NEGATIVE_DIGEST_MISMATCH  ALLOW ... stage=EXECUTION => DIGEST_MISMATCH

D1 attested  = 22055b0016c31920d3ddb38d01edb288b3c5da8592cd3a4b79d1967822483fc9
D2 committed = 6974161efd584b69dee44981aeaf173cfa9de106a1299d3855a1228cd8ab5a8a
```

## Comparing S5 against S3

S3 and S5 in `s5-negative/` differ in one declared place. Same authority
epoch, same `env_id`, same effector metadata, a fresh `command_id` each. The
one mutation: after our payload was fixed and its digest attested,
`args.limit` in the transmitted bytes went from 50 to 51. The package records
the mutation, both digests, and the transmitted bytes, so D2 can be checked
as `sha256(transmitted_payload)`.

On your side, all three S5 records carry D2 and the EXECUTION record shows
`applied: true`. On ours, the entry for that `command_id` attests ALLOW over
D1. Each record is internally consistent within its own chain; only the
pairing shows the disagreement.

## Tamper checks run on the reproducer

Each tampered input was confirmed to differ from the original before running:

- `applied` flipped on your EXECUTION records → your chain fails at records 5 and 8, exit 1
- your S5 digests rewritten to D1 to hide the mismatch → your chain fails at 6, 7, 8, exit 1, verdicts marked UNTRUSTED
- our S5 attested digest rewritten to D2 to hide the mismatch → our chain fails at seq 4, exit 1

## Not covered

- A mutation made inside the box after its ALLOW. At `b3050fd2`, `CommitEvidence`
  records only the input digest, so no record on either side would carry D2.
- One host, one run per capture, no concurrency, no clock skew.
- Our chain is held in memory for these runs and its head is not anchored.
- No EABC conformance level is claimed.
