#!/usr/bin/env python3
"""Validation Run 002: standalone reproducer.

Imports nothing from either implementation. Python 3.8+ standard library only.

    python3 reproduce.py AUTHORITY.jsonl CONTROLLER.json

It does four things, all from the two raw files:
  1. recomputes the authority hash chain from its published field order
  2. recomputes the controller hash chain from its published recipe
  3. pairs records by command_id alone (no timestamps, no ordering, no index)
  4. applies the controller's reconcile rules and prints one verdict per act

Step 4 is a line-for-line port of the controller's shipped reconcile()
(TypeScript). The port was checked to produce identical output to the shipped
function on every capture in this bundle; the shipped output is included
alongside as reconcile-output.shipped.txt.
"""
import hashlib
import json
import sys

GENESIS = "0" * 64

# ---- authority side: halos-1.3-atl-analysis poc/evidence.py _HASH_FIELD_ORDER
AUTH_FIELDS = [
    "stage", "command_id", "env_id", "action_digest", "execution_epoch",
    "authority_epoch", "authorization_decision", "authorization_reason",
    "safety_decision", "safety_reason", "commit_decision", "commit_reason",
    "execution_outcome", "applied", "timestamp",
]


def authority_chain(records):
    prev, bad = GENESIS, []
    for i, r in enumerate(records):
        body = "".join(json.dumps(r[f], separators=(",", ":")) for f in AUTH_FIELDS)
        h = hashlib.sha256((prev + body).encode("utf-8")).hexdigest()
        if r["prev_hash"] != prev or r["record_hash"] != h:
            bad.append(i)
        prev = r["record_hash"]
    return bad


# ---- controller side: entry_hash = sha256(JSON array, fixed order, UTF-8)
def controller_entries(pkg):
    """Rebuild the controller's verdict entries from the package.

    Each executed observation references its entry by seq. Where PREPARE and
    COMMIT share a seq (S3, S5: one decision, one entry), COMMIT is the entry.
    """
    by_seq = {}
    for s in pkg["scenarios"]:
        if s["status"] != "EXECUTED":
            continue
        p, c = s["prepare"], s["commit"]
        by_seq.setdefault(p["evidence_ref"]["seq"], dict(
            ref=p["evidence_ref"], command_id=p["command_id"], env_id=p["env_id"],
            epoch=p["authority_epoch"], payload_digest=p["payload_digest"],
            decision="ALLOW", reason="", at=p["at"]))
        by_seq[c["evidence_ref"]["seq"]] = dict(
            ref=c["evidence_ref"], command_id=c["command_id"], env_id=c["env_id"],
            epoch=c["authority_epoch_at_decision"], payload_digest=c["payload_digest"],
            decision="ALLOW" if c["final_authorization_outcome"] == "ALLOW" else "BLOCK",
            reason=c.get("implementation_reason", ""), at=c["at"])
    return [dict(e, seq=k) for k, e in sorted(by_seq.items())]


def controller_chain(entries):
    prev, bad = GENESIS, []
    for e in entries:
        canonical = json.dumps(
            [e["seq"], e["command_id"], e["env_id"], e["epoch"], e["payload_digest"],
             e["decision"], e["reason"], e["at"], prev],
            separators=(",", ":"), ensure_ascii=False)
        h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if h != e["ref"]["entry_hash"]:
            bad.append(e["seq"])
        prev = h
    return bad


# ---- reconcile: port of the controller's shipped reconcile()
def committed(t):
    if t.get("applied") is True:
        return True
    if t.get("applied") is False:
        return False
    if t.get("authorization_decision") == "BLOCK":
        return False
    return t.get("execution_outcome") == "COMMITTED"


def reconcile(ours, theirs):
    if theirs is None:
        return "MATCH_REFUSED" if ours["decision"] == "BLOCK" else "MISSING_COUNTERPART", ""
    if ours["command_id"] != theirs["command_id"]:
        return "NOT_A_PAIR", ""
    if ours["decision"] == "BLOCK":
        return ("UNEXPECTED_COMMIT", "") if committed(theirs) else ("MATCH_REFUSED", "")
    if ours["payload_digest"] != theirs["action_digest"]:
        return "DIGEST_MISMATCH", f"ours {ours['payload_digest']} vs committed {theirs['action_digest']}"
    return "MATCH", ""


def main(auth_path, ctrl_path):
    theirs = [json.loads(l) for l in open(auth_path, encoding="utf-8") if l.strip()]
    pkg = json.load(open(ctrl_path, encoding="utf-8"))
    entries = controller_entries(pkg)

    a_bad, c_bad = authority_chain(theirs), controller_chain(entries)
    print(f"authority chain : {len(theirs)} records, "
          f"{'VERIFIED' if not a_bad else 'FAILED at ' + str(a_bad)}")
    print(f"controller chain: {len(entries)} entries, "
          f"{'VERIFIED' if not c_bad else 'FAILED at seq ' + str(c_bad)}")
    print(f"provenance      : {pkg['provenance']}")
    if a_bad or c_bad:
        print()
        print("!! A CHAIN FAILED TO VERIFY. The verdicts below are computed from")
        print("!! records whose integrity is broken and MUST NOT be read as findings.")
    print()

    # One terminal controller entry per act: the last entry per command_id.
    terminal = {}
    for e in entries:
        terminal[e["command_id"]] = e
    scenario_of = {s["prepare"]["command_id"]: s["scenario"]
                   for s in pkg["scenarios"] if s["status"] == "EXECUTED"}

    for cid, ours in terminal.items():
        cands = [t for t in theirs if t["command_id"] == cid]
        counterpart = (next((t for t in cands if t["stage"] == "EXECUTION"), None)
                       or next((t for t in cands if t["stage"] == "COMMIT"), None))
        status, detail = reconcile(ours, counterpart)
        print(f"{'UNTRUSTED ' if a_bad or c_bad else ''}{scenario_of.get(cid, '?'):<28} {ours['decision']:<5} {cid}  "
              f"stage={counterpart['stage'] if counterpart else 'NONE':<9} => {status}"
              f"{' (' + detail + ')' if detail else ''}")

    for s in pkg["scenarios"]:
        if s.get("mutation"):
            m = s["mutation"]
            print(f"\n{s['scenario']} declared mutation: {m['description']}")
            print(f"  D1 attested  = {m['attested_payload_digest']}")
            print(f"  D2 committed = {m['committed_artifact_digest']}")
            print(f"  D2 == sha256(transmitted bytes): "
                  f"{hashlib.sha256(m['transmitted_payload'].encode('utf-8')).hexdigest() == m['committed_artifact_digest']}")
        elif s["status"] != "EXECUTED":
            print(f"\n{s['scenario']}: {s['status']}")

    return 1 if a_bad or c_bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
