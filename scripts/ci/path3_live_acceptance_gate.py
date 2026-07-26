#!/usr/bin/env python3
"""Fail-closed acceptance gate for one signed PATH-3 live run."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "runtime-verification/generated/runtime_evidence_ledger.json"
ATTEST = ROOT / "scripts/ci/path3_run_attestation.py"
POLICY = ROOT / "scripts/ci/path3_attestation_policy.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument("--max-age-seconds", type=int, default=86400)
    args = parser.parse_args()
    path = args.attestation if args.attestation.is_absolute() else ROOT / args.attestation
    if not os.getenv("PATH3_ATTESTATION_KEY"):
        print("PATH3_ATTESTATION_KEY is required")
        return 1

    import subprocess
    import sys

    if subprocess.run(
        [sys.executable, str(ATTEST), "check", "--attestation", str(path)], cwd=ROOT, check=False
    ).returncode:
        return 1
    if subprocess.run(
        [
            sys.executable,
            str(POLICY),
            "--attestation",
            str(path),
            "--max-age-seconds",
            str(args.max_age_seconds),
        ],
        cwd=ROOT,
        check=False,
    ).returncode:
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    selected = set(payload.get("selected_services") or [])
    bound = {row.get("service") for row in payload.get("evidence_files") or []}
    errors: list[str] = []
    if not selected:
        errors.append("empty_selected_services")
    if selected != bound:
        errors.append("selected_evidence_set_mismatch")
    if args.require_all:
        planned = {row["service"] for row in ledger["services"] if row.get("probeable")}
        if selected != planned:
            errors.append("not_all_probeable_services_selected")
    by_service = {row["service"]: row for row in ledger["services"]}
    for service in sorted(selected):
        row = by_service.get(service)
        if not row or not row.get("runtime_verified"):
            errors.append(f"{service}:not_runtime_verified")
            continue
        latest = row.get("latest_valid_evidence") or {}
        for field in (
            "run_id",
            "tested_sha",
            "environment_id",
            "compose_config_sha256",
            "targets_file_sha256",
        ):
            if latest.get(field) != payload.get(field):
                errors.append(f"{service}:{field}_mismatch")
    if payload.get("production_certified") is not False:
        errors.append("production_certification_must_remain_false")
    if errors:
        print("PATH-3 live acceptance BLOCKED: " + ", ".join(sorted(set(errors))))
        return 1
    print(f"PATH-3 live acceptance PASS: {len(selected)} services, run={payload['run_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
