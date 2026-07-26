from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_capability_registry_guard_is_clean() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ci/capability_registry_guard.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_capability_ids_are_unique() -> None:
    data = json.loads(
        (ROOT / "capabilities/registry/capabilities.json").read_text(encoding="utf-8")
    )
    ids = [c["id"] for c in data["capabilities"]]
    assert len(ids) == len(set(ids))


def test_no_capability_is_production_certified_without_runtime_evidence() -> None:
    data = json.loads(
        (ROOT / "capabilities/registry/capabilities.json").read_text(encoding="utf-8")
    )
    for c in data["capabilities"]:
        if c["production_certified"]:
            assert c["maturity"] == 5 and c["evidence_level"] == 5
            assert all(c["runtime"][k] for k in ("metrics", "traces", "receipts", "audit_events"))
