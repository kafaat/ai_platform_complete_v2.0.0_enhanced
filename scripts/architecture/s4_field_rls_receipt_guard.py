#!/usr/bin/env python3
"""Fail-closed validator for subject-bound S4 field-management live RLS receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "services/field-management-service/main.py"
ASSERTION = ROOT / "shared/security/service_tenant_assertion.py"
SCHEMA = "sahool.s4-field-rls-live-evidence/v2"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_identity() -> dict[str, str]:
    return {
        "main_sha256": _sha(MAIN),
        "service_tenant_assertion_sha256": _sha(ASSERTION),
    }


def findings(receipt: dict[str, Any], subject_sha: str) -> list[str]:
    out: list[str] = []
    if receipt.get("schema") != SCHEMA:
        out.append("receipt schema mismatch")
    if receipt.get("subject_sha") != subject_sha.lower():
        out.append("receipt subject SHA mismatch")
    if receipt.get("status") != "PASSED":
        out.append("receipt status is not PASSED")
    if receipt.get("service") != "field-management-service":
        out.append("service identity mismatch")
    if receipt.get("source_identity") != _source_identity() or receipt.get("source_identity_match") is not True:
        out.append("deployed field source identity mismatch")
    if receipt.get("owner_or_superuser_proof_accepted") is not False:
        out.append("owner/superuser proof must be rejected")
    if receipt.get("authority_promotion") is not False:
        out.append("evidence collector must not promote authority")

    role = receipt.get("application_role") or {}
    if not isinstance(role.get("name"), str) or not role.get("name", "").strip():
        out.append("application role name missing")
    for key in ("superuser", "bypassrls", "createdb", "createrole"):
        if role.get(key) is not False:
            out.append(f"application role must have {key}=false")
    if role.get("reachable_privileged_role_count") != 0:
        out.append("application role reaches privileged role membership")

    isolation = receipt.get("tenant_isolation") or {}
    if not isolation.get("tenant_a") or not isolation.get("tenant_b"):
        out.append("tenant identities missing")
    elif isolation.get("tenant_a") == isolation.get("tenant_b"):
        out.append("tenant isolation requires two distinct tenants")
    if not isolation.get("field_id"):
        out.append("field identity missing")
    if isolation.get("owner_http") != 200:
        out.append("owner tenant did not receive HTTP 200")
    if isolation.get("cross_tenant_http") != 404:
        out.append("cross-tenant read was not hidden as HTTP 404")

    auth = receipt.get("authentication") or {}
    if auth.get("missing_token_http") != 401 or auth.get("wrong_token_http") != 401:
        out.append("service-token negative controls failed")

    try:
        observed = datetime.fromisoformat(str(receipt.get("observed_at")).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError
    except Exception:
        out.append("invalid observed_at")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipt", required=True)
    ap.add_argument("--subject-sha", required=True)
    args = ap.parse_args()
    if len(args.subject_sha) not in (40, 64) or any(c not in "0123456789abcdefABCDEF" for c in args.subject_sha):
        print("s4_field_rls_receipt_fail invalid subject sha")
        return 1
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    problems = findings(receipt, args.subject_sha)
    if problems:
        for problem in problems:
            print("s4_field_rls_receipt_fail", problem)
        return 1
    print(f"s4_field_rls_receipt_ok role={receipt['application_role']['name']} subject={args.subject_sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
