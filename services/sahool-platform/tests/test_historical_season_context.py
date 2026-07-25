from datetime import date

from core.historical_season_context import (
    build_simulation_outcome,
    compose_historical_season_context,
)


def _context(**overrides):
    kwargs = {
        "tenant_id": "tenant-a",
        "field_id": "field-a",
        "season_id": "season-a",
        "season": {"season_id": "season-a", "sowing_date": date(2025, 1, 1)},
        "season_record": {"id": "record-a", "trust_status": "accepted"},
        "crop": {"crop_registry_ref": "wheat"},
        "events": [],
        "harvest": None,
        "vegetation": [],
        "weather": [],
    }
    kwargs.update(overrides)
    return compose_historical_season_context(**kwargs)


def test_context_is_deterministic_and_content_addressed():
    a = _context(events=[{"id": "2", "event_date": "2025-02-02"}])
    b = _context(events=[{"event_date": "2025-02-02", "id": "2"}])
    assert a == b
    assert len(a["input_digest"]) == 64


def test_only_measured_high_confidence_irrigation_influences_simulation():
    out = _context(
        events=[
            {
                "id": "a",
                "event_type": "irrigation",
                "event_date": "2025-01-02",
                "amount_mm": 12,
                "low_confidence": False,
            },
            {
                "id": "b",
                "event_type": "irrigation",
                "event_date": "2025-01-03",
                "amount_mm": 99,
                "low_confidence": True,
            },
            {
                "id": "c",
                "event_type": "irrigation",
                "event_date": "2025-01-04",
                "duration_hours": 2,
                "amount_mm": None,
                "low_confidence": False,
            },
        ]
    )
    assert out["simulation_inputs"]["irrigation_mm_total"] == 12.0
    assert out["quality"]["irrigation_measurement_count"] == 1


def test_cloud_qualified_ndvi_produces_observed_fapar_without_daily_invention():
    out = _context(
        vegetation=[
            {"id": 1, "acquisition_date": "2025-01-10", "ndvi_mean": 0.5, "cloud_pct": 5},
            {"id": 2, "acquisition_date": "2025-01-20", "ndvi_mean": 0.8, "cloud_pct": 80},
            {"id": 3, "acquisition_date": "2025-01-30", "ndvi_mean": 0.6, "cloud_pct": None},
        ]
    )
    assert out["vegetation"]["observation_count"] == 1
    assert out["simulation_inputs"]["observed_fapar"] == 0.452
    assert out["quality"]["no_daily_fapar_interpolation"] is True


def test_missing_manual_record_and_satellite_are_explicit():
    out = _context(season_record=None)
    assert out["manual_record"]["status"] == "empty"
    assert out["vegetation"]["status"] == "empty"
    assert out["simulation_inputs"] == {
        "irrigation_mm_total": None,
        "observed_fapar": None,
    }


def _outcome(**overrides):
    kwargs = {
        "result": {
            "yield_kg_ha": 4000.0,
            "yield_low_kg_ha": 3200.0,
            "yield_high_kg_ha": 4800.0,
            "confidence": 0.6,
            "water_stress_factor": 0.9,
        },
        "engine_name": "sahool-season-sim",
        "engine_version": "1",
        "parameter_version": "sahool-season-defaults/1",
        "harvest": None,
    }
    kwargs.update(overrides)
    return build_simulation_outcome(kwargs.pop("result"), **kwargs)


def test_outcome_carries_engine_identity_and_prediction_band():
    out = _outcome()
    assert out["engine"] == {
        "name": "sahool-season-sim",
        "version": "1",
        "parameter_version": "sahool-season-defaults/1",
    }
    assert out["prediction"]["yield_low_kg_ha"] == 3200.0
    assert out["prediction"]["yield_high_kg_ha"] == 4800.0
    assert out["prediction"]["confidence"] == 0.6


def test_outcome_without_harvest_is_explicit_not_invented():
    out = _outcome(harvest=None)
    assert out["expected_vs_actual"]["status"] == "no_actual_yield"
    assert out["expected_vs_actual"]["predicted_yield_kg_ha"] == 4000.0


def test_outcome_with_null_harvest_yield_reports_no_actual():
    out = _outcome(harvest={"yield_kg_ha": None})
    assert out["expected_vs_actual"]["status"] == "no_actual_yield"


def test_outcome_compares_actual_within_uncertainty_band():
    out = _outcome(harvest={"yield_kg_ha": 4200})
    eva = out["expected_vs_actual"]
    assert eva["status"] == "compared"
    assert eva["actual_yield_kg_ha"] == 4200.0
    assert eva["delta_kg_ha"] == 200.0
    assert round(eva["relative_error"], 6) == round(200.0 / 4200.0, 6)
    assert eva["actual_within_uncertainty_band"] is True


def test_outcome_flags_actual_outside_uncertainty_band():
    out = _outcome(harvest={"yield_kg_ha": 2000})
    eva = out["expected_vs_actual"]
    assert eva["status"] == "compared"
    assert eva["delta_kg_ha"] == -2000.0
    assert eva["actual_within_uncertainty_band"] is False


def test_outcome_zero_actual_guards_relative_error():
    out = _outcome(harvest={"yield_kg_ha": 0})
    assert out["expected_vs_actual"]["relative_error"] is None
