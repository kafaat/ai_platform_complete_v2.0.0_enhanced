#!/usr/bin/env python3
"""Fail closed on a Decision SoR live-closure receipt that is not subject-bound and complete."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = "sahool.s5-decision-live-closure/v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SOR_TABLES = (
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
    "online_learning_updates",
)


def findings_for(receipt: dict[str, Any], subject_sha: str) -> list[str]:
    findings: list[str] = []
    if receipt.get("schema") != SCHEMA:
        findings.append("schema_mismatch")
    if not _SHA_RE.fullmatch(subject_sha) or receipt.get("subject_sha") != subject_sha:
        findings.append("subject_sha_mismatch")
    if receipt.get("classification") != "PASSED":
        findings.append("classification_not_passed")
    if receipt.get("read_only") is not True:
        findings.append("collector_not_read_only")
    if receipt.get("authority_promotion") is not False:
        findings.append("collector_must_not_promote_authority")
    claims = receipt.get("claims") or {}
    if claims.get("post_cutover_platform_write_enforcement_proven") is not True:
        findings.append("write_enforcement_claim_not_proven")
    # The current collector cannot inspect historical DB/audit logs.  Reject any receipt that
    # overclaims this fact; post-cutover effective denial is the measured claim.
    if claims.get("historical_zero_platform_writes_measured") is not False:
        findings.append("historical_zero_writes_overclaim")
    if receipt.get("findings") not in ([], None):
        findings.append("receipt_contains_findings")

    observed = receipt.get("observed_at")
    try:
        dt = datetime.fromisoformat(str(observed))
        if dt.tzinfo is None:
            raise ValueError("naive")
    except Exception:
        findings.append("observed_at_invalid")

    ev = receipt.get("evidence") or {}
    for key, service in (
        ("decision_runtime_identity", "decision-service"),
        ("platform_runtime_identity", "sahool-platform"),
    ):
        ident = ev.get(key) or {}
        if not (
            ident.get("service") == service
            and ident.get("git_sha") == subject_sha
            and ident.get("metadata_source") == "immutable-image-file"
        ):
            findings.append(f"{key}_mismatch")

    ready = ev.get("decision_ready") or {}
    db = ready.get("db_readiness") or {}
    if not (
        ready.get("ready") is True
        and ready.get("status") == "ready"
        and ready.get("sor_enabled") is True
        and ready.get("mode") == "system-of-record"
        and db.get("db_reachable") is True
        and db.get("migrations_current") is True
    ):
        findings.append("decision_ready_not_closed")

    cut = ev.get("decision_cutover_readiness") or {}
    if not (
        cut.get("requested_sor") is True
        and cut.get("can_enable_sor") is True
        and cut.get("production_approved") is True
        and cut.get("can_demote_platform") is True
        and not (cut.get("missing_gates") or [])
    ):
        findings.append("decision_cutover_not_closed")

    pm = (ev.get("platform_ready") or {}).get("decision_sor") or {}
    if not (
        pm.get("requested_mode") == "decision_service_sor"
        and pm.get("effective_mode") == "decision_service_sor"
        and pm.get("platform_writes_required") is False
        and pm.get("strict_decision_service_required") is True
        and pm.get("demotion_allowed") is True
        and not (pm.get("missing_gates") or [])
    ):
        findings.append("platform_not_effectively_demoted")

    role = ev.get("role_certification") or {}
    if not (
        role.get("classification") == "PASSED"
        and role.get("cutover_preflight_safe") is True
        and role.get("role_separation_confirmed") is True
        and not (role.get("blockers") or [])
    ):
        findings.append("role_certification_not_safe")
    platform_role = str(role.get("platform_role") or "")
    if not platform_role:
        findings.append("platform_role_missing")

    privilege = ev.get("platform_privilege_check") or {}
    if privilege.get("action") != "check" or privilege.get("role") != platform_role:
        findings.append("platform_privilege_check_identity_mismatch")
    state = privilege.get("after") or {}
    for table in SOR_TABLES:
        p = state.get(table) or {}
        for name in ("INSERT", "UPDATE", "DELETE"):
            if p.get(name) is not False:
                findings.append(f"{table}:{name}:effective_write_not_denied")
        if p.get("SELECT") is not True:
            findings.append(f"{table}:SELECT:not_retained")
    return sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipt", required=True, type=Path)
    ap.add_argument("--subject-sha", required=True)
    args = ap.parse_args(argv)
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    findings = findings_for(receipt, args.subject_sha.strip().lower())
    if findings:
        print("s5_decision_live_closure_receipt_guard_failed")
        for item in findings:
            print(f" - {item}")
        return 1
    print("s5_decision_live_closure_receipt_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
