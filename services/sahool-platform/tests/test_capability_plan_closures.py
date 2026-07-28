from datetime import date

import pytest
from core.canonical_field_state import compose_canonical_field_state
from core.economic_scenarios import compare_economic_scenarios
from core.equipment_intelligence import summarize_equipment
from core.field_digital_twin import build_field_twin_from_canonical_state
from core.yield_intelligence import build_canonical_yield_state


def weather():
    return {
        "schema_version": "wx10/canonical-weather-state/1.0.0",
        "state_id": "w1",
        "products": {"gdd": {"gdd_cumulative": 400}},
    }


def water():
    return {"schema_version": "canonical_water_state.v1", "depletion_mm": 60, "taw_mm": 100}


def soil():
    return {"schema_version": "canonical_soil_state.v1", "soil_texture": "loam"}


def spectral():
    return {"schema_version": "canonical_spectral_state.v1", "ndvi": 0.72}


def test_canonical_field_state_is_deterministic_and_fail_closed():
    a = compose_canonical_field_state(
        field_id="f1",
        season_id="s1",
        as_of_time="2026-07-28T00:00:00Z",
        weather=weather(),
        water=water(),
        soil=soil(),
        spectral=spectral(),
    )
    b = compose_canonical_field_state(
        field_id="f1",
        season_id="s1",
        as_of_time="2026-07-28T00:00:00Z",
        weather=weather(),
        water=water(),
        soil=soil(),
        spectral=spectral(),
    )
    assert a.operational_eligible and a.state_digest == b.state_digest
    blocked = compose_canonical_field_state(
        field_id="f1",
        season_id="s1",
        as_of_time="x",
        weather={"foo": "bar"},
        water=water(),
        soil=soil(),
    )
    assert not blocked.operational_eligible
    assert "weather_noncanonical_schema" in blocked.limitations


def test_field_twin_is_thin_canonical_view():
    state = compose_canonical_field_state(
        field_id="f1",
        season_id="s1",
        as_of_time="x",
        weather=weather(),
        water=water(),
        soil=soil(),
        spectral=spectral(),
    )
    twin = build_field_twin_from_canonical_state(state.to_dict())
    assert twin.risks["water_stress"] == "medium"
    assert twin.current["ndvi"] == 0.72
    with pytest.raises(ValueError):
        build_field_twin_from_canonical_state({"field_id": "f1"})


def test_yield_state_requires_valid_trueup_range_and_keeps_quality():
    state = build_canonical_yield_state(
        field_id="f",
        season_id="s",
        source_sha256="abc",
        records=[{"yield_kg_ha": 1000}, {"yield_kg_ha": 1200}, {"yield_kg_ha": "bad"}],
        calibration_factor=1.1,
    )
    assert state.raw_mean_kg_ha == 1100
    assert state.calibrated_mean_kg_ha == 1210
    assert state.quality_status == "accepted_with_warning"
    with pytest.raises(ValueError):
        build_canonical_yield_state(
            field_id="f", season_id="s", source_sha256="abc", records=[], calibration_factor=2
        )


def test_equipment_intelligence_reports_due_and_unavailable_without_telemetry_claim():
    state = summarize_equipment(
        assets=[
            {
                "id": "tractor-1",
                "status": "active",
                "operating_hours": 300,
                "last_service_hours": 0,
                "service_interval_hours": 250,
            },
            {
                "id": "pump-1",
                "status": "maintenance",
                "operating_hours": 20,
                "next_service_date": "2026-07-01",
            },
        ],
        as_of=date(2026, 7, 28),
    )
    assert state.service_due == 2
    assert state.unavailable == 1
    assert state.readiness == "degraded"


def test_economic_scenarios_rank_only_comparable_margins():
    baseline = {
        "expected_yield_t_ha": 5,
        "crop_price_per_t": 100,
        "irrigation_m3_ha": 100,
        "water_price_per_m3": 1,
        "energy_kwh_ha": 10,
        "energy_price_per_kwh": 2,
        "fertilizer_kg_ha": 10,
        "fertilizer_price_per_kg": 3,
    }
    better = {**baseline, "scenario_id": "better", "expected_yield_t_ha": 6}
    partial = {"scenario_id": "partial", "expected_yield_t_ha": 7}
    result = compare_economic_scenarios(
        baseline=baseline, alternatives=[partial, better], currency="YER"
    )
    assert result["best_comparable_scenario_id"] == "better"
    assert result["alternatives"][0]["comparable"] is False
