from pathlib import Path

from scripts.ci.service_feature_ui_contract_gate import run_gate

ROOT = Path(__file__).resolve().parents[1]


def test_service_feature_ui_contract_gate_passes_current_inventory():
    ok, result = run_gate(ROOT, ROOT / "config/service_feature_ui_contracts.json")
    assert ok, result["failures"]
    assert result["service_count"] == 26
    assert result["failed"] == 0


def test_service_feature_ui_contract_gate_tracks_backend_only_services():
    ok, result = run_gate(ROOT, ROOT / "config/service_feature_ui_contracts.json")
    assert ok
    by_name = {row["service"]: row for row in result["services"]}
    for name in [
        "sam2-inference",
        "rag-retrieval",
        "knowledge-graph",
        "weather-signal-engine",
        "raster-tiler-service",
        "erp-bridge",
    ]:
        row = by_name[name]
        assert row["status"] == "pass"
        assert any(evidence["match_count"] > 0 for evidence in row["evidence"])
