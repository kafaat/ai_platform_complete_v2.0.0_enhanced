#!/usr/bin/env python3
"""A′-4c — compatibility projection convergence and non-authority preservation gate."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "capabilities/registry/capabilities.json"
PROJECTION = ROOT / "scripts/ci/capability_projection_sync.py"
CHECKS = (
    ("traceability", ROOT / "scripts/ci/capability_linker.py", ["--check"]),
    ("runtime_instrumentation", ROOT / "scripts/ci/capability_runtime_evidence.py", ["--check"]),
    ("projection", PROJECTION, ["--check"]),
    ("reconciliation", ROOT / "scripts/ci/capability_shadow_reconciliation.py", ["--check"]),
)


def _projection_module():
    spec = importlib.util.spec_from_file_location("projection_roundtrip", PROJECTION)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def inspect() -> list[str]:
    findings = []
    before = json.loads(LEGACY.read_text(encoding="utf-8"))
    m = _projection_module()
    drift, synced, canonical = m.drift()
    if drift:
        findings.extend("projection_drift:" + x for x in drift)
    canonical = set(canonical)
    b = {x["id"]: x for x in before["capabilities"]}
    a = {x["id"]: x for x in synced["capabilities"]}
    if set(b) != set(a):
        findings.append("identity_changed_by_projection")
    for cid in sorted(set(b) & set(a)):
        for field in sorted(set(b[cid]) | set(a[cid])):
            if field not in canonical and b[cid].get(field) != a[cid].get(field):
                findings.append(f"projection_touched_foreign_field:{cid}:{field}")
    for label, path, args in CHECKS:
        p = subprocess.run(
            [sys.executable, str(path), *args],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        if p.returncode:
            findings.append(f"{label}_check_failed")
    return findings


def main() -> int:
    findings = inspect()
    if findings:
        print("capability_compatibility_roundtrip: FAIL")
        [print(" ", x) for x in findings]
        return 1
    print("capability_compatibility_roundtrip_ok drift=0 foreign_field_changes=0 checks=4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
