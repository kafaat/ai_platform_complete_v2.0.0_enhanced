"""C2 Crop Twin + verified-learning authority contract."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services/sahool-platform"
if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))

from core.field_digital_twin import build_field_twin_from_canonical_state  # noqa: E402


def _canonical_state() -> dict:
    return {
        "schema_version": "canonical_field_state.v1",
        "field_id": "f-1",
        "season_id": "s-1",
        "as_of_time": "2026-08-17T12:00:00Z",
        "operational_eligible": True,
        "state_digest": "state-digest-1",
        "evidence_digests": {
            "weather": "dw",
            "water": "dwa",
            "soil": "ds",
            "spectral": "dsp",
        },
        "limitations": [],
        "weather": {
            "schema_version": "wx10/canonical-weather-state/1.0.0",
            "state_id": "wx-state-1",
            "source_snapshot_id": "wx-snap-1",
            "quality_status": "validated",
            "products": {"current": {"temperature_c": 28.5}},
        },
        "water": {
            "schema_version": "canonical_water_state.v1",
            "depletion_mm": 55.0,
            "taw_mm": 100.0,
            "raw_mm": 50.0,
            "root_depth_m": 1.2,
        },
        "soil": {
            "schema_version": "soil-profile.v1",
            "profile_id": "soil-1",
            "quality_status": "verified",
            "layers": [{"texture_class": "loam"}],
        },
        "spectral": {
            "schema": "canonical_spectral_state.v1",
            "indices": {"ndvi": 0.71, "ndre": 0.22, "ndmi": -0.05, "msi": 1.6},
            "acquisition_date": "2026-08-15",
        },
    }


def test_twin_reads_current_owner_schema_and_preserves_evidence_identity():
    twin = build_field_twin_from_canonical_state(_canonical_state())
    assert twin.current["ndvi"] == pytest.approx(0.71)
    assert twin.current["soil_texture"] == "loam"
    assert twin.current["weather_state_id"] == "wx-state-1"
    assert twin.current["season_id"] == "s-1"
    assert twin.current["as_of_time"] == "2026-08-17T12:00:00Z"
    assert twin.current["weather_snapshot_id"] == "wx-snap-1"
    assert twin.current["canonical_evidence_digests"]["spectral"] == "dsp"
    assert twin.risks["water_stress"] == "medium"
    assert "no_execution_authority" in twin.assumptions


def test_platform_learning_path_has_no_legacy_execution_ledger_fallback():
    text = (PLATFORM / "api/routers/decision_impact.py").read_text(encoding="utf-8")
    start = text.index("async def get_learning(")
    end = text.index('@router.get("/api/v1/decision/economics")', start)
    body = text[start:end]
    assert "get_calibration_dataset" in body
    assert "_collect_impact_records" not in body
    assert "decision-service/verified-calibration-dataset" in body
    assert 'dataset.get("authoritative") is not True' in body


def test_internal_twin_learning_is_same_route_and_verified_only():
    text = (PLATFORM / "api/routers/internal_service.py").read_text(encoding="utf-8")
    assert text.count('@router.get("/internal/fields/{field_id}/state")') == 1
    assert "build_field_twin_from_canonical_state" in text
    assert "get_calibration_dataset" in text
    assert "authoritative_verified_dataset_unavailable" in text
    assert '"auto_promoted": False' in text
    start = text.index("async def internal_field_state(")
    end = text.index('@router.post("/internal/events/ai-advice")', start)
    body = text[start:end]
    assert "_collect_impact_records" not in body
    assert "FROM execution_ledger" not in body


def test_decision_calibration_dataset_filters_field_season_after_verified_gate():
    persistence = (ROOT / "services/decision-service/persistence.py").read_text(encoding="utf-8")
    main = (ROOT / "services/decision-service/main.py").read_text(encoding="utf-8")
    assert "o.verification_state IN ('verified_success','verified_failure')" in persistence
    assert "($4::text IS NULL OR d.field_id=$4)" in persistence
    assert "($5::text IS NULL OR d.season_id=$5)" in persistence
    assert '"by_decision_type": by_decision_type' in persistence
    assert "field_id: str | None = Query(default=None)" in main
    assert "season_id: str | None = Query(default=None)" in main


def test_internal_twin_learning_resolves_active_season_and_fails_closed_without_one():
    text = (PLATFORM / "api/routers/internal_service.py").read_text(encoding="utf-8")
    assert "load_active_season_id" in text
    assert "season_id=season_id" in text
    assert "authoritative_verified_dataset_unavailable:no_active_season" in text
    # Cross-season learning must never be the implicit fallback when active season is absent.
    learning_start = text.index("if learning_model_id:")
    learning_end = text.index('@router.post("/internal/events/ai-advice")', learning_start)
    body = text[learning_start:learning_end]
    assert "if not season_id:" in body
    assert "season_id=season_id" in body


def test_twin_preserves_temporal_and_season_identity_even_when_ineligible():
    state = _canonical_state()
    state["operational_eligible"] = False
    state["limitations"] = ["weather_missing"]
    twin = build_field_twin_from_canonical_state(state)
    assert twin.current["season_id"] == "s-1"
    assert twin.current["as_of_time"] == "2026-08-17T12:00:00Z"
    assert twin.current["canonical_state_digest"] == "state-digest-1"
