from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/capability_release_history.py"

spec = importlib.util.spec_from_file_location("capability_release_history", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_release_history_has_three_ordered_validated_baselines() -> None:
    data = module.build()
    assert data["release_count"] == 3
    assert [row["sequence"] for row in data["releases"]] == [1, 2, 3]
    assert all(row["capabilities"] == 81 for row in data["releases"])


def test_release_history_never_infers_runtime_or_production() -> None:
    data = module.build()
    assert data["constraints"]["runtime_claims"] is False
    assert data["constraints"]["production_certification_inferred"] is False
    assert all(row["runtime_verified"] == 0 for row in data["releases"])
    assert all(row["production_certified"] == 0 for row in data["releases"])


def test_static_adjudication_release_changes_only_reviewed_capabilities() -> None:
    data = module.build()
    adjudication_release = data["releases"][1]
    assert adjudication_release["added_from_previous"] == []
    assert adjudication_release["removed_from_previous"] == []
    assert adjudication_release["modified_from_previous"] == [
        "INT-004",
        "IRR-010",
        "OPS-001",
        "OPS-006",
        "OPS-008",
    ]
    assert adjudication_release["human_adjudications_applied"] == 13
    assert adjudication_release["capabilities_mapped"] == 80
    assert adjudication_release["capabilities_unmapped"] == 1


def test_pa003_implementation_release_changes_only_pa003() -> None:
    data = module.build()
    latest = data["releases"][-1]
    assert latest["added_from_previous"] == []
    assert latest["removed_from_previous"] == []
    assert latest["modified_from_previous"] == ["PA-003"]
    assert latest["human_adjudications_applied"] == 13
    assert latest["capabilities_mapped"] == 81
    assert latest["capabilities_unmapped"] == 0
    assert latest["runtime_verified"] == 0
    assert latest["production_certified"] == 0


def test_release_history_outputs_have_no_drift() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_pa003_is_mapped_only_by_traceable_implementation_evidence() -> None:
    mapping = json.loads(
        (ROOT / "docs/capability-registry/generated/mapping/capability_mapping.json").read_text(
            encoding="utf-8"
        )
    )
    by_id = {row["capability_id"]: row for row in mapping["capabilities"]}
    pa003 = by_id["PA-003"]
    assert pa003["mapped"] is True
    assert pa003["coverage_dimensions"] >= 4
    assert pa003["governance"] == []
    assert pa003["runtime_verified"] is False
    assert pa003["production_certified"] is False
