from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/capability_evidence_maturity_engine.py"
OUT = ROOT / "docs/capability-registry/generated/evidence"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True
    )


def test_evidence_maturity_has_no_drift() -> None:
    result = run("--check")
    assert result.returncode == 0, result.stderr


def test_matrix_covers_registry_exactly() -> None:
    registry = json.loads(
        (ROOT / "docs/capability-registry/generated/capability_registry.json").read_text()
    )
    matrix = json.loads((OUT / "capability_evidence_matrix.json").read_text())
    assert {c["id"] for c in registry["capabilities"]} == {
        c["capability_id"] for c in matrix["capabilities"]
    }
    assert matrix["summary"]["capability_count"] == 81


def test_fail_closed_maturity_rules() -> None:
    matrix = json.loads((OUT / "capability_evidence_matrix.json").read_text())
    assert matrix["constraints"]["automatic_registry_update"] is False
    assert matrix["constraints"]["runtime_required_for_level_4"] is True
    assert matrix["constraints"]["production_required_for_level_5"] is True
    for record in matrix["capabilities"]:
        assert 0 <= record["assessed_maturity"] <= 5
        if record["assessed_maturity"] >= 4:
            assert record["runtime_verified"] is True
        if record["assessed_maturity"] == 5:
            assert record["production_certified"] is True
        assert record["automatic_registry_update"] is False


def test_runtime_instrumentation_is_not_runtime_proof() -> None:
    matrix = json.loads((OUT / "capability_evidence_matrix.json").read_text())
    instrumented = [r for r in matrix["capabilities"] if r["evidence"]["runtime_instrumentation"]]
    assert instrumented
    assert all(not r["runtime_verified"] for r in matrix["capabilities"])
    assert all(not r["production_certified"] for r in matrix["capabilities"])


def test_manifest_covers_all_generated_files() -> None:
    manifest = json.loads((OUT / "evidence_manifest.json").read_text())
    assert set(manifest) == {
        "CAPABILITY_EVIDENCE_MATURITY_REPORT.md",
        "capability_evidence_matrix.csv",
        "capability_evidence_matrix.json",
        "capability_maturity_baseline.csv",
        "capability_maturity_baseline.json",
        "domain_maturity_summary.json",
    }
