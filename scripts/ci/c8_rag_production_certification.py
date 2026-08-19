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
    return 0 if status in {"PASS", "EVIDENCE_REQUIRED", "CERTIFIED_CUTOVER_CAPABLE"} else 1


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--receipt")
    a.add_argument("--subject-sha")
    x = a.parse_args(argv)
    f = []
    for rel in (
        "scripts/architecture/rag_authority_convergence_guard.py",
        "scripts/ci/rag_operational_boundary_guard.py",
    ):
        rc, out = run(rel)
        if rc:
            f.append(f"canonical_guard_failed:{rel}:{out[-500:]}")
    if f:
        return emit("C8", "FAILED", f)
    if not x.receipt:
        return emit("C8", "EVIDENCE_REQUIRED", ["live_rag_parity_receipt_missing"])
    if not x.subject_sha:
        return emit("C8", "FAILED", ["subject_sha_required_with_receipt"])
    rc, out = run(
        "scripts/architecture/rag_live_parity_receipt_guard.py",
        "--receipt",
        x.receipt,
        "--subject-sha",
        x.subject_sha,
    )
    return emit(
        "C8",
        "CERTIFIED_CUTOVER_CAPABLE" if rc == 0 else "FAILED",
        [] if rc == 0 else ["canonical_live_receipt_guard_failed", out[-800:]],
    )


if __name__ == "__main__":
    raise SystemExit(main())
