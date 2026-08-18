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


LEGACY = ROOT / "services/sahool-platform/core/knowledge_graph/sqlite_graph.py"


def main():
    f = []
    if LEGACY.exists():
        f.append("legacy_kg_platform_store_present")
    rc, out = run("scripts/architecture/platform_shrink_ratchet_guard.py")
    if rc:
        f.append("platform_shrink_ratchet_guard_failed:" + out[-800:])
    return emit(
        "C13",
        "PASS" if not f else "FAILED",
        f,
        physical_shrink_authorized=False,
        already_closed=not LEGACY.exists(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
