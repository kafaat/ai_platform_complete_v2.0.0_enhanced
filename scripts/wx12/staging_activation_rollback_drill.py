"""Fail-closed staging drill verifier. It validates externally supplied evidence JSON."""

from __future__ import annotations
import json, os, sys

REQUIRED = [
    "candidate_digest",
    "previous_digest",
    "activation_receipt_digest",
    "active_state_after_activation",
    "rollback_receipt_digest",
    "active_state_after_rollback",
]


def main(path: str):
    if os.getenv("SAHOOL_ENV", "").lower() != "staging":
        raise SystemExit("SAHOOL_ENV=staging required")
    d = json.load(open(path, encoding="utf-8"))
    missing = [k for k in REQUIRED if not d.get(k)]
    if missing:
        raise SystemExit(f"missing evidence: {missing}")
    if (
        d["candidate_digest"] != d["activation_receipt_digest"]
        or d["candidate_digest"] != d["active_state_after_activation"]
    ):
        raise SystemExit("activation evidence digest mismatch")
    if (
        d["previous_digest"] != d["rollback_receipt_digest"]
        or d["previous_digest"] != d["active_state_after_rollback"]
    ):
        raise SystemExit("rollback evidence digest mismatch")
    print(json.dumps({"ok": True, "drill": "activation_rollback", "environment": "staging"}))


if __name__ == "__main__":
    main(sys.argv[1])
