#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(rel, *args):
    p = subprocess.run(
        [sys.executable, str(ROOT / rel), *map(str, args)],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
    )
    return p.returncode, (p.stdout or "").strip()


def emit(stage, status, findings=(), **extra):
    o = {
        "schema": f"sahool.{stage.lower()}-certification/v2",
        "stage": stage,
        "status": status,
        "authority_changed": False,
        "findings": list(findings),
        **extra,
    }
    print(json.dumps(o, indent=2, sort_keys=True))
    return 0 if status in {"PASS", "EVIDENCE_REQUIRED", "LIVE_EVIDENCE_VERIFIED"} else 1


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--subject-sha")
    args = parser.parse_args(argv)
    guards = (
        "scripts/ci/model_promotion_decision_boundary_gate.py",
        "scripts/ci/model_activation_request_boundary_gate.py",
        "scripts/ci/model_activation_approval_boundary_gate.py",
        "scripts/ci/model_registry_activation_boundary_gate.py",
        "scripts/ci/wx11_closed_loop_completion_gate.py",
    )
    findings = []
    for rel in guards:
        rc, out = run(rel)
        if rc:
            findings.append(f"canonical_guard_failed:{rel}:{out[-500:]}")
    if findings:
        return emit("C12", "FAILED", findings, promotion_permitted=False)
    if args.receipt is None and args.subject_sha is None:
        return emit(
            "C12",
            "EVIDENCE_REQUIRED",
            ["live_model_activation_evidence_required"],
            promotion_permitted=False,
            automatic_promotion=False,
            ready_for_authority_adjudication=False,
        )
    if args.receipt is None or args.subject_sha is None:
        return emit(
            "C12",
            "FAILED",
            ["receipt_and_subject_sha_must_be_supplied_together"],
            promotion_permitted=False,
            automatic_promotion=False,
            ready_for_authority_adjudication=False,
        )
    rc, out = run(
        "scripts/staging/c12_live_activation_receipt.py",
        "verify",
        "--receipt",
        args.receipt,
        "--subject-sha",
        args.subject_sha,
    )
    if rc:
        return emit(
            "C12",
            "FAILED",
            ["canonical_live_activation_receipt_failed", out[-1000:]],
            subject_sha=args.subject_sha,
            promotion_permitted=False,
            automatic_promotion=False,
            ready_for_authority_adjudication=False,
        )
    return emit(
        "C12",
        "LIVE_EVIDENCE_VERIFIED",
        [],
        subject_sha=args.subject_sha,
        promotion_permitted=False,
        automatic_promotion=False,
        ready_for_authority_adjudication=True,
        next_action="independent human adjudication under GATE-01",
    )


if __name__ == "__main__":
    raise SystemExit(main())
