from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/capability_parity_investment_engine.py"
OUT = ROOT / "docs/capability-registry/generated/benchmark"
spec = importlib.util.spec_from_file_location("capability_parity", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True
    )


def test_committed_outputs_have_no_drift() -> None:
    result = run("--check")
    assert result.returncode == 0, result.stderr


def test_build_covers_registry_and_fails_closed() -> None:
    parity, investment, heat = mod.build()
    assert len(parity["capabilities"]) == 81
    assert len(investment["capabilities"]) == 81
    assert len(heat["domains"]) == 10
    assert all(
        row["classification"] in {"Leader", "Parity", "Behind", "Missing", "Unassessed"}
        for row in parity["capabilities"]
    )
    assert all(row["runtime_verified"] is False for row in parity["capabilities"])
    assert all(row["production_certified"] is False for row in parity["capabilities"])


def test_legacy_identifier_collisions_are_rebased_to_canonical_ids() -> None:
    parity, _, _ = mod.build()
    rows = {row["capability_id"]: row for row in parity["capabilities"]}
    # Legacy INT-001 meant ERP; canonical INT-001 is Public API and SDK.
    assert rows["INT-001"]["title"] == "Public API and SDK"
    assert rows["FM-008"]["title"] == "ERP integration"
    # Legacy IRR-007 meant recommendation; canonical IRR-007 is pump/valve control.
    assert rows["IRR-007"]["title"] == "Pump and valve control"
    assert rows["IRR-007"]["benchmark_coverage"] == "unassessed"
    assert rows["IRR-005"]["title"] == "Irrigation recommendation"


def test_adjacent_eta_evidence_cannot_score_et0() -> None:
    parity, _, _ = mod.build()
    rows = {row["capability_id"]: row for row in parity["capabilities"]}
    assert rows["WX-004"]["competitor_scores"]["CropX"] is None
    assert rows["WX-004"]["benchmark_coverage"] == "unassessed"
    evidence, score_map = mod.load_competitor_evidence(mod.registry_index()[1])
    assert any(
        row["capability_id"] == "WX-004" and row["comparison_scope"] == "adjacent"
        for row in evidence
    )
    assert ("WX-004", "CropX") not in score_map


def test_every_direct_score_has_canonical_evidence_references() -> None:
    parity, _, _ = mod.build()
    for row in parity["capabilities"]:
        for platform, score in row["competitor_scores"].items():
            refs = row["competitor_evidence_refs"][platform]
            confidence = row["competitor_score_confidence"][platform]
            if score is None:
                assert refs == []
                assert confidence is None
            else:
                assert refs
                assert confidence in {"low", "medium", "high"}


def test_approved_phase3_decisions_target_canonical_capabilities() -> None:
    _, investment, _ = mod.build()
    rows = {row["capability_id"]: row for row in investment["capabilities"]}
    assert rows["PA-005"]["decision"] == "PARTNER/INTEGRATE"
    assert rows["PA-005"]["approved"] is True
    assert rows["IRR-009"]["decision"] == "BUILD"
    assert rows["FM-008"]["decision"] == "BUILD CORE + CONNECTORS"
    assert rows["INT-001"]["approved"] is False


def test_check_detects_committed_output_drift(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mod, "OUT", tmp_path)
    outputs = mod.render_outputs()
    mod.write(outputs)
    assert mod.check(outputs) == []
    target = tmp_path / "capability_parity_matrix.json"
    target.write_text("{}\n", encoding="utf-8")
    assert "drift:capability_parity_matrix.json" in mod.check(outputs)


def test_manifest_binds_all_inputs_and_outputs() -> None:
    manifest = json.loads((OUT / "benchmark_manifest.json").read_text())
    assert (
        "docs/capability-registry/benchmark/source/sahool_capability_assessments.csv"
        in manifest["inputs"]
    )
    assert "docs/capability-registry/benchmark/BENCHMARK_SCORING_RUBRIC.md" in manifest["inputs"]
    assert set(manifest["outputs"]) == {
        "CAPABILITY_PARITY_INVESTMENT_REPORT.md",
        "capability_investment_matrix.csv",
        "capability_investment_matrix.json",
        "capability_parity_matrix.csv",
        "capability_parity_matrix.json",
        "domain_heat_map.json",
    }
