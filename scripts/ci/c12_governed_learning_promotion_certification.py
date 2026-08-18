#!/usr/bin/env python3
from __future__ import annotations

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


def main():
    guards = (
        "scripts/ci/model_promotion_decision_boundary_gate.py",
        "scripts/ci/model_activation_request_boundary_gate.py",
        "scripts/ci/model_activation_approval_boundary_gate.py",
        "scripts/ci/model_registry_activation_boundary_gate.py",
        "scripts/ci/wx11_closed_loop_completion_gate.py",
    )
    f = []
    for rel in guards:
        rc, out = run(rel)
        if rc:
            f.append(f"canonical_guard_failed:{rel}:{out[-500:]}")
    if f:
        return emit("C12", "FAILED", f, promotion_permitted=False)
    return emit(
        "C12",
        "EVIDENCE_REQUIRED",
        ["live_model_activation_evidence_required"],
        promotion_permitted=False,
        automatic_promotion=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
