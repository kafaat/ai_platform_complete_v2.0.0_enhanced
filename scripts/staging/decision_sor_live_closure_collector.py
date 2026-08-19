#!/usr/bin/env python3
"""Read-only, subject-bound live closure collector for the Decision SoR cutover.

This collector NEVER performs REVOKE/GRANT and never writes business data.  It composes four
independent live facts after an operator-controlled cutover:
  1) immutable build identities for decision-service and sahool-platform match the reviewed SHA;
  2) decision-service is ready in system-of-record mode and its production cutover gates allow
     platform demotion;
  3) the deployed platform reports effective ``decision_service_sor`` mode on its existing
     ``/readyz`` surface (no new route); and
  4) PostgreSQL role topology is cutover-safe and the platform role has NO effective
     INSERT/UPDATE/DELETE on the five SoR tables while SELECT remains available.

The DB checks delegate to the canonical role-certification and privilege tools in ``--check``
mode.  A PASSED receipt proves post-cutover enforcement.  It deliberately does *not* claim that
historical zero platform writes were measured before the observation instant.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import request

ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "services" / "decision-service"
SCHEMA = "sahool.s5-decision-live-closure/v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SOR_TABLES = (
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
    "online_learning_updates",
)


def _headers(token: str = "") -> dict[str, str]:
    h = {"accept": "application/json"}
    if token:
        h["authorization"] = f"Bearer {token}"
    return h


def _json_get(url: str, *, token: str = "", timeout: float = 10.0) -> dict[str, Any]:
    req = request.Request(url, method="GET", headers=_headers(token))
    with request.urlopen(req, timeout=timeout) as res:  # noqa: S310 - operator-provided live URL
        if not 200 <= int(res.status) < 300:
            raise RuntimeError(f"GET {url} returned HTTP {res.status}")
        body = json.loads(res.read().decode("utf-8") or "{}")
    if not isinstance(body, dict):
        raise RuntimeError(f"GET {url} did not return a JSON object")
    return body


def _run_json(cmd: list[str], *, env: dict[str, str]) -> dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
        check=False,
    )
    raw = (proc.stdout or "").strip()
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"command emitted non-JSON (exit={proc.returncode}): {raw[-500:]}"
        ) from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed exit={proc.returncode}: {json.dumps(body, sort_keys=True)[:1000]}"
        )
    if not isinstance(body, dict):
        raise RuntimeError("command JSON must be an object")
    return body


def _identity_ok(identity: dict[str, Any], service: str, subject_sha: str) -> bool:
    return (
        identity.get("service") == service
        and identity.get("git_sha") == subject_sha
        and identity.get("metadata_source") == "immutable-image-file"
    )


def _effective_privilege_findings(privilege_check: dict[str, Any], platform_role: str) -> list[str]:
    findings: list[str] = []
    if privilege_check.get("action") != "check":
        findings.append("privilege_tool_must_run_check_mode")
    if privilege_check.get("role") != platform_role:
        findings.append("privilege_role_mismatch")
    state = privilege_check.get("after")
    if not isinstance(state, dict):
        return findings + ["effective_privilege_state_missing"]
    for table in SOR_TABLES:
        privs = state.get(table)
        if not isinstance(privs, dict):
            findings.append(f"{table}:privilege_state_missing")
            continue
        for privilege in ("INSERT", "UPDATE", "DELETE"):
            if privs.get(privilege) is not False:
                findings.append(f"{table}:{privilege}:effective_write_not_denied")
        if privs.get("SELECT") is not True:
            findings.append(f"{table}:SELECT:read_facade_not_retained")
    return findings


def evaluate_evidence(
    *,
    subject_sha: str,
    decision_identity: dict[str, Any],
    platform_identity: dict[str, Any],
    decision_ready: dict[str, Any],
    decision_cutover: dict[str, Any],
    platform_ready: dict[str, Any],
    role_certification: dict[str, Any],
    privilege_check: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    """Pure fail-closed evaluator, split out so mutation tests do not require live services."""
    findings: list[str] = []
    if not _SHA_RE.fullmatch(subject_sha):
        findings.append("subject_sha_invalid")
    if not _identity_ok(decision_identity, "decision-service", subject_sha):
        findings.append("decision_runtime_identity_mismatch")
    if not _identity_ok(platform_identity, "sahool-platform", subject_sha):
        findings.append("platform_runtime_identity_mismatch")

    db = decision_ready.get("db_readiness") or {}
    if not (
        decision_ready.get("status") == "ready"
        and decision_ready.get("ready") is True
        and decision_ready.get("service") == "decision-service"
        and decision_ready.get("sor_enabled") is True
        and decision_ready.get("mode") == "system-of-record"
        and db.get("db_reachable") is True
        and db.get("migrations_current") is True
    ):
        findings.append("decision_service_not_ready_as_current_sor")

    if not (
        decision_cutover.get("requested_sor") is True
        and decision_cutover.get("can_enable_sor") is True
        and decision_cutover.get("production_approved") is True
        and decision_cutover.get("can_demote_platform") is True
        and not (decision_cutover.get("missing_gates") or [])
    ):
        findings.append("decision_cutover_readiness_not_closed")

    p_mode = platform_ready.get("decision_sor") or {}
    if not (
        p_mode.get("requested_mode") == "decision_service_sor"
        and p_mode.get("effective_mode") == "decision_service_sor"
        and p_mode.get("platform_writes_required") is False
        and p_mode.get("mirror_required") is False
        and p_mode.get("strict_decision_service_required") is True
        and p_mode.get("demotion_allowed") is True
        and not (p_mode.get("missing_gates") or [])
    ):
        findings.append("platform_runtime_not_effectively_demoted")

    if not (
        role_certification.get("classification") == "PASSED"
        and role_certification.get("cutover_preflight_safe") is True
        and role_certification.get("role_separation_confirmed") is True
        and not (role_certification.get("blockers") or [])
    ):
        findings.append("role_certification_not_safe")
    platform_role = str(role_certification.get("platform_role") or "")
    if not platform_role:
        findings.append("platform_role_missing")
    else:
        findings.extend(_effective_privilege_findings(privilege_check, platform_role))

    normalized = {
        "decision_runtime_identity": decision_identity,
        "platform_runtime_identity": platform_identity,
        "decision_ready": decision_ready,
        "decision_cutover_readiness": decision_cutover,
        "platform_ready": {"decision_sor": p_mode},
        "role_certification": role_certification,
        "platform_privilege_check": privilege_check,
    }
    return sorted(set(findings)), normalized


def collect(args: argparse.Namespace) -> dict[str, Any]:
    subject_sha = args.subject_sha.strip().lower()
    env = os.environ.copy()
    decision = args.decision_url.rstrip("/")
    platform = args.platform_url.rstrip("/")
    token = os.getenv("DECISION_SERVICE_AUTH_TOKEN", "").strip()

    decision_identity = _json_get(decision + "/runtime-identity", token=token)
    decision_ready = _json_get(decision + "/readyz", token=token)
    decision_cutover = _json_get(decision + "/v1/cutover/readiness", token=token)
    platform_identity = _json_get(platform + "/runtime-identity")
    platform_ready = _json_get(platform + "/readyz")
    role_cert = _run_json([sys.executable, str(DECISION / "decision_sor_role_certify.py")], env=env)
    privilege = _run_json(
        [sys.executable, str(DECISION / "platform_sor_revoke.py"), "--check"], env=env
    )
    findings, evidence = evaluate_evidence(
        subject_sha=subject_sha,
        decision_identity=decision_identity,
        platform_identity=platform_identity,
        decision_ready=decision_ready,
        decision_cutover=decision_cutover,
        platform_ready=platform_ready,
        role_certification=role_cert,
        privilege_check=privilege,
    )
    return {
        "schema": SCHEMA,
        "subject_sha": subject_sha,
        "observed_at": datetime.now(UTC).isoformat(),
        "classification": "PASSED" if not findings else "FAILED",
        "read_only": True,
        "authority_promotion": False,
        "claims": {
            "post_cutover_platform_write_enforcement_proven": not findings,
            "historical_zero_platform_writes_measured": False,
        },
        "findings": findings,
        "evidence": evidence,
    }


def _write(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject-sha", required=True)
    ap.add_argument(
        "--decision-url", default=os.getenv("DECISION_SERVICE_URL", "http://localhost:8097")
    )
    ap.add_argument(
        "--platform-url", default=os.getenv("SAHOOL_PLATFORM_URL", "http://localhost:8000")
    )
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        receipt = collect(args)
    except Exception as exc:  # live harness: preserve failure as evidence, never fabricate PASS
        receipt = {
            "schema": SCHEMA,
            "subject_sha": str(args.subject_sha).strip().lower(),
            "observed_at": datetime.now(UTC).isoformat(),
            "classification": "FAILED",
            "read_only": True,
            "authority_promotion": False,
            "claims": {
                "post_cutover_platform_write_enforcement_proven": False,
                "historical_zero_platform_writes_measured": False,
            },
            "findings": [f"collector_error:{type(exc).__name__}:{exc}"],
            "evidence": {},
        }
    _write(args.output, receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt.get("classification") == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
