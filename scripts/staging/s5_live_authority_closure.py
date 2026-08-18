#!/usr/bin/env python3
"""Operational S5 live-authority evidence runner.

This script composes the three existing authority evidence collectors/guards without creating a
new authority model.  It never edits ``authority_cutovers.json`` and never promotes an authority.
A green bundle means only that the reviewed subject has subject-bound live evidence for Decision,
Field and Knowledge Graph and is READY FOR EXPLICIT AUTHORITY ADJUDICATION.

Collection intentionally keeps secrets in environment variables.  Tokens/DSNs are never copied
into the output bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "sahool.s5-live-authority-closure-bundle/v1"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")

RECEIPTS = {
    "decision": {
        "filename": "decision-live-closure.json",
        "guard": "scripts/architecture/s5_decision_live_closure_receipt_guard.py",
        "receipt_schema": "sahool.s5-decision-live-closure/v1",
    },
    "field_management": {
        "filename": "field-rls-live-evidence.json",
        "guard": "scripts/architecture/s4_field_rls_receipt_guard.py",
        "receipt_schema": "sahool.s4-field-rls-live-evidence/v2",
    },
    "knowledge_graph": {
        "filename": "kg-runtime-parity.json",
        "guard": "scripts/architecture/s4_kg_runtime_parity_receipt_guard.py",
        "receipt_schema": "sahool.s4-kg-runtime-parity/v2",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"receipt_not_object:{path}")
    return value


def _run(cmd: list[str], *, env: dict[str, str] | None = None, timeout: int = 600) -> dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "output": (proc.stdout or "")[-4000:],
    }


def _guard(path: Path, *, subject_sha: str, guard_rel: str) -> dict[str, Any]:
    result = _run(
        [sys.executable, str(ROOT / guard_rel), "--receipt", str(path), "--subject-sha", subject_sha],
        timeout=120,
    )
    return {
        "passed": result["returncode"] == 0,
        "returncode": result["returncode"],
        "output": result["output"],
    }


def verify_receipts(
    *,
    subject_sha: str,
    decision_receipt: Path,
    field_receipt: Path,
    kg_receipt: Path,
) -> dict[str, Any]:
    """Verify all three live receipts using their canonical guards.

    This function deliberately does not duplicate domain validation logic.  The authoritative
    receipt validators remain the three existing guards; the bundle adds only cross-receipt
    subject binding and a non-promoting aggregate verdict.
    """
    subject_sha = subject_sha.strip().lower()
    findings: list[str] = []
    if not _SHA40.fullmatch(subject_sha):
        findings.append("subject_sha_must_be_full_40_hex_commit")

    paths = {
        "decision": decision_receipt,
        "field_management": field_receipt,
        "knowledge_graph": kg_receipt,
    }
    rows: dict[str, Any] = {}
    for name, path in paths.items():
        meta = RECEIPTS[name]
        if not path.is_file():
            findings.append(f"{name}:receipt_missing")
            rows[name] = {"path": str(path), "guard_passed": False, "missing": True}
            continue
        try:
            receipt = _load(path)
        except Exception as exc:
            findings.append(f"{name}:receipt_unreadable:{type(exc).__name__}")
            rows[name] = {"path": str(path), "guard_passed": False, "unreadable": True}
            continue

        if receipt.get("schema") != meta["receipt_schema"]:
            findings.append(f"{name}:receipt_schema_mismatch")
        if receipt.get("subject_sha") != subject_sha:
            findings.append(f"{name}:subject_sha_mismatch")
        if receipt.get("authority_promotion") is not False:
            findings.append(f"{name}:receipt_must_not_promote_authority")

        guard = _guard(path, subject_sha=subject_sha, guard_rel=str(meta["guard"]))
        if not guard["passed"]:
            findings.append(f"{name}:canonical_guard_failed")
        rows[name] = {
            "path": str(path),
            "sha256": _sha256(path),
            "receipt_schema": receipt.get("schema"),
            "subject_sha": receipt.get("subject_sha"),
            "observed_at": receipt.get("observed_at"),
            "guard_passed": guard["passed"],
            "guard_returncode": guard["returncode"],
            "guard_output": guard["output"],
        }

    findings = sorted(set(findings))
    evidence_complete = not findings and all(row.get("guard_passed") is True for row in rows.values())
    return {
        "schema": SCHEMA,
        "subject_sha": subject_sha,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "classification": "PASSED" if evidence_complete else "FAILED",
        "live_evidence_complete": evidence_complete,
        "ready_for_authority_adjudication": evidence_complete,
        "authority_promotion": False,
        # A receipt bundle is evidence, not the adjudication itself.  Physical deletion remains
        # blocked until the authority contract is explicitly changed and its end-state guards pass.
        "physical_shrink_authorized": False,
        "findings": findings,
        "receipts": rows,
    }


def _write(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _required_env(names: tuple[str, ...]) -> list[str]:
    return [name for name in names if not os.getenv(name, "").strip()]


def preflight(subject_sha: str) -> dict[str, Any]:
    subject_sha = subject_sha.strip().lower()
    missing_env = _required_env(
        (
            # Decision database proof
            "DECISION_SOR_PLATFORM_URL",
            "DECISION_SOR_SERVICE_URL",
            "DECISION_SOR_ADMIN_DATABASE_URL",
            "DECISION_SOR_PLATFORM_ROLE",
            # Field restricted-role proof
            "DATABASE_URL",
            "SAHOOL_AGENT_TOKEN",
            # Field/KG runtime targets and identities
            "FIELD_SERVICE_URL",
            "TENANT_A",
            "TENANT_B",
            "FIELD_A",
            "KG_SERVICE_URL",
            "KG_TENANT_ID",
        )
    )
    missing_tools = [tool for tool in ("git", "curl", "psql") if shutil.which(tool) is None]
    findings: list[str] = []
    if not _SHA40.fullmatch(subject_sha):
        findings.append("subject_sha_must_be_full_40_hex_commit")
    elif shutil.which("git") is not None:
        head = _run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], timeout=10)
        actual = head["output"].strip().lower() if head["returncode"] == 0 else ""
        if not _SHA40.fullmatch(actual):
            findings.append("live_collection_requires_real_git_checkout")
        elif actual != subject_sha:
            findings.append(f"checkout_subject_sha_mismatch:{actual}")
    findings.extend(f"missing_env:{name}" for name in missing_env)
    findings.extend(f"missing_tool:{name}" for name in missing_tools)
    return {
        "schema": "sahool.s5-live-authority-preflight/v1",
        "subject_sha": subject_sha,
        "classification": "PASSED" if not findings else "FAILED",
        "findings": findings,
        "authority_promotion": False,
    }


def collect(args: argparse.Namespace) -> dict[str, Any]:
    subject_sha = args.subject_sha.strip().lower()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()

    pre = preflight(subject_sha)
    _write(out_dir / "preflight.json", pre)
    if pre["classification"] != "PASSED":
        return {
            "schema": SCHEMA,
            "subject_sha": subject_sha,
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "classification": "FAILED",
            "live_evidence_complete": False,
            "ready_for_authority_adjudication": False,
            "authority_promotion": False,
            "physical_shrink_authorized": False,
            "findings": ["live_preflight_failed", *pre["findings"]],
            "receipts": {},
        }

    decision = out_dir / RECEIPTS["decision"]["filename"]
    field = out_dir / RECEIPTS["field_management"]["filename"]
    kg = out_dir / RECEIPTS["knowledge_graph"]["filename"]
    collector_results: dict[str, Any] = {}

    collector_results["decision"] = _run(
        [
            sys.executable,
            str(ROOT / "scripts/staging/decision_sor_live_closure_collector.py"),
            "--subject-sha",
            subject_sha,
            "--decision-url",
            args.decision_url,
            "--platform-url",
            args.platform_url,
            "--output",
            str(decision),
        ],
        env=env,
    )

    field_env = env.copy()
    field_env["EXPECTED_SHA"] = subject_sha
    field_env["FIELD_RLS_EVIDENCE_OUT"] = str(field)
    collector_results["field_management"] = _run(
        ["bash", str(ROOT / "scripts/staging/field_management_live_gate.sh")],
        env=field_env,
    )

    collector_results["knowledge_graph"] = _run(
        [
            sys.executable,
            str(ROOT / "scripts/staging/kg_runtime_parity_collector.py"),
            "--base-url",
            os.environ["KG_SERVICE_URL"],
            "--tenant-id",
            os.environ["KG_TENANT_ID"],
            "--subject-sha",
            subject_sha,
            "--out",
            str(kg),
        ],
        env=env,
    )

    bundle = verify_receipts(
        subject_sha=subject_sha,
        decision_receipt=decision,
        field_receipt=field,
        kg_receipt=kg,
    )
    bundle["collector_results"] = {
        name: {
            "returncode": result["returncode"],
            "output": result["output"],
        }
        for name, result in collector_results.items()
    }
    if any(result["returncode"] != 0 for result in collector_results.values()):
        bundle["classification"] = "FAILED"
        bundle["live_evidence_complete"] = False
        bundle["ready_for_authority_adjudication"] = False
        bundle["findings"] = sorted(set([*bundle["findings"], "one_or_more_collectors_failed"]))
    return bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_pre = sub.add_parser("preflight")
    p_pre.add_argument("--subject-sha", required=True)
    p_pre.add_argument("--output", type=Path)

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--subject-sha", required=True)
    p_verify.add_argument("--decision-receipt", required=True, type=Path)
    p_verify.add_argument("--field-receipt", required=True, type=Path)
    p_verify.add_argument("--kg-receipt", required=True, type=Path)
    p_verify.add_argument("--output", required=True, type=Path)

    p_collect = sub.add_parser("collect")
    p_collect.add_argument("--subject-sha", required=True)
    p_collect.add_argument("--out-dir", required=True, type=Path)
    p_collect.add_argument("--decision-url", default=os.getenv("DECISION_SERVICE_URL", "http://localhost:8097"))
    p_collect.add_argument("--platform-url", default=os.getenv("SAHOOL_PLATFORM_URL", "http://localhost:8000"))
    p_collect.add_argument("--bundle-output", type=Path)

    args = parser.parse_args(argv)
    if args.command == "preflight":
        body = preflight(args.subject_sha)
        if args.output:
            _write(args.output, body)
    elif args.command == "verify":
        body = verify_receipts(
            subject_sha=args.subject_sha,
            decision_receipt=args.decision_receipt,
            field_receipt=args.field_receipt,
            kg_receipt=args.kg_receipt,
        )
        _write(args.output, body)
    else:
        body = collect(args)
        output = args.bundle_output or (args.out_dir / "s5-live-authority-bundle.json")
        _write(output, body)

    print(json.dumps(body, sort_keys=True))
    return 0 if body.get("classification") == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
