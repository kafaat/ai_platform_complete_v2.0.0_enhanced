from datetime import date

from core.historical_season_context import compose_historical_season_context


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
