"""Adapters + PIT field-history composer (pure logic)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agronomic_adapters as a
from field_history import compose


def test_crop_card_adapter_hashes_parameters():
    out = a.crop_card_to_model(
        {
            "crop_id": "wheat",
            "cultivar_id": "x",
            "version": "v1",
            "base_temp_c": 5,
            "gdd_to_maturity": 1500,
            "max_yield_kg_ha": 6000,
            "harvest_index": 0.45,
            "water_use_efficiency": 18,
        }
    )
    assert len(out["parameter_set_hash"]) == 64
    assert out["crop_card_version"] == "v1"


def test_crop_card_missing_parameters_fail_closed():
    with pytest.raises(ValueError, match="crop_card_missing"):
        a.crop_card_to_model({"crop_id": "wheat"})


def test_soil_adapter_computes_available_water():
    out = a.soil_profile_to_model(
        {
            "soil_profile_id": "s",
            "field_capacity": 0.30,
            "wilting_point": 0.15,
            "rootable_depth_cm": 100,
            "bulk_density": 1.3,
        }
    )
    assert out["available_water_mm"] == 150.0


def test_soil_hydraulics_are_validated():
    with pytest.raises(ValueError, match="soil_hydraulics_invalid"):
        a.soil_profile_to_model(
            {
                "soil_profile_id": "s",
                "field_capacity": 0.10,
                "wilting_point": 0.20,
                "rootable_depth_cm": 100,
                "bulk_density": 1.3,
            }
        )


def test_weather_series_requires_complete_days():
    with pytest.raises(ValueError, match="weather_day_missing:0"):
        a.weather_series_to_model({"daily": [{"date": "2026-01-01", "tmin": 5}]})


def test_irrigation_adapter_uses_efficiency():
    out = a.irrigation_to_model(
        {"application_efficiency": 0.8},
        {"irrigation_events": [{"depth_mm": 10}, {"depth_mm": 5}]},
    )
    assert out["irrigation_mm"] == 12.0
    assert out["gross_irrigation_mm"] == 15.0


def test_history_excludes_future_available_records():
    h = compose(
        "f",
        "s",
        "2026-01-02T00:00:00Z",
        [
            {"id": "a", "data_available_at": "2026-01-01T00:00:00Z"},
            {"id": "b", "data_available_at": "2026-01-03T00:00:00Z"},
        ],
    )
    assert [r["id"] for r in h["records"]] == ["a"]
    assert h["record_count"] == 1 and len(h["snapshot_hash"]) == 64
