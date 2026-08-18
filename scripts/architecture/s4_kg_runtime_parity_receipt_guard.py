#!/usr/bin/env python3
"""Fail-closed validator for S4 Knowledge Graph live runtime-parity receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "docs/architecture/s4_kg_consumer_freeze.json"
CASES = ROOT / "docs/architecture/evidence/s4_kg_parity_cases.json"
MAIN = ROOT / "services/knowledge-graph/main.py"
STORE = ROOT / "services/knowledge-graph/kg_store.py"
GATEWAY = ROOT / "shared/security/gateway_deps.py"
SCHEMA = "sahool.s4-kg-runtime-parity/v2"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_identity() -> dict[str, str]:
    return {
        "main_sha256": _sha(MAIN),
        "kg_store_sha256": _sha(STORE),
        "gateway_deps_sha256": _sha(GATEWAY),
    }


def findings(receipt: dict[str, Any], subject_sha: str) -> list[str]:
    out: list[str] = []
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if receipt.get("schema") != SCHEMA:
        out.append("receipt schema mismatch")
    if receipt.get("subject_sha") != subject_sha.lower():
        out.append("receipt subject SHA mismatch")
    if receipt.get("local_subject_sha") != subject_sha.lower() or receipt.get("local_subject_match") is not True:
        out.append("collector checkout subject SHA mismatch")
    if receipt.get("status") != "PASSED":
        out.append("receipt status is not PASSED")
    if receipt.get("read_only") is not True or receipt.get("authority_promotion") is not False:
        out.append("receipt must be read-only and non-promoting")
    ready = receipt.get("ready") or {}
    if ready.get("status") != "ready" or ready.get("service") != "knowledge-graph":
        out.append("canonical KG readiness mismatch")
    expected_identity = _source_identity()
    if receipt.get("expected_source_identity") != expected_identity:
        out.append("expected source identity drift")
    if receipt.get("source_identity") != expected_identity or receipt.get("source_identity_match") is not True:
        out.append("deployed source identity mismatch")
    if receipt.get("cases_sha256") != _sha(CASES):
        out.append("parity cases digest mismatch")
    if receipt.get("consumer_freeze_sha256") != _sha(FREEZE):
        out.append("consumer freeze digest mismatch")
    if receipt.get("consumer_fingerprint_sha256") != freeze.get("consumer_fingerprint_sha256"):
        out.append("consumer fingerprint mismatch")
    rows = receipt.get("cases")
    if not isinstance(rows, list) or len(rows) != len(cases) or receipt.get("case_count") != len(cases):
        out.append("parity case count mismatch")
    else:
        for expected, row in zip(cases, rows, strict=True):
            if not isinstance(row, dict) or row.get("case") != expected:
                out.append("parity case identity/order mismatch")
                continue
            minimum = int(expected["min_edges"])
            if row.get("status") != "PASSED" or row.get("parity") is not True:
                out.append(f"parity failed for {expected['subject_id']}")
            if row.get("minimum_evidence_met") is not True:
                out.append(f"minimum evidence flag failed for {expected['subject_id']}")
            if int(row.get("rest_count", 0)) < minimum or int(row.get("graphql_count", 0)) < minimum:
                out.append(f"empty/insufficient evidence for {expected['subject_id']}")
            digest = row.get("edge_digest")
            if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
                out.append(f"invalid edge digest for {expected['subject_id']}")
    if receipt.get("non_empty_case_count") != len(cases):
        out.append("not every parity case produced live evidence")
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
        print("s4_kg_runtime_parity_receipt_fail invalid subject sha")
        return 1
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    problems = findings(receipt, args.subject_sha)
    if problems:
        for problem in problems:
            print("s4_kg_runtime_parity_receipt_fail", problem)
        return 1
    print(f"s4_kg_runtime_parity_receipt_ok cases={receipt['case_count']} subject={args.subject_sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
