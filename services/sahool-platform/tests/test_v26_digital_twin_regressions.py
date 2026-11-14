"""v26 digital-twin truth/physics guards: no fictitious moisture or growth evidence."""

from __future__ import annotations

import pytest
from api.crop_decision_bridge import build_crop_decision_candidate
from api.crop_twin import TwinDay, crop_twin_state
from core.field_digital_twin import (
    FieldTwinState,
    build_field_twin_from_canonical_state,
    simulate_irrigation,
)

pytestmark = pytest.mark.unit


def _crop(gdd_product):
    return crop_twin_state(
        "wheat",
        [TwinDay(t_min_c=10, t_max_c=24, et0_mm=4, kc=1)],
        taw_mm=100,
        raw_fraction=0.5,
        field_id="field-1",
        season_id="season-1",
        gdd_product=gdd_product,
    )


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -1.0, True])
def test_canonical_gdd_missing_or_invalid_is_not_zero_growth(value):
    out = _crop({"accumulated_gdd": value, "series_quality_status": "insufficient"})
    assert out["phenology"]["status"] == "unavailable"
    assert out["phenology"]["gdd_cumulative"] is None
    assert out["phenology"]["stage"] is None
    assert out["nutrient"]["uptake_to_date_kg_ha"] is None
    assert out["crop_intelligence"]["phenology"]["status"] == "unavailable"
    assert "canonical_gdd_value_unavailable" in out["crop_intelligence"]["limitations"]


def test_canonical_gdd_observed_zero_remains_real_zero():
    out = _crop({"accumulated_gdd": 0.0, "series_quality_status": "validated"})
    assert out["phenology"]["status"] == "available"
    assert out["phenology"]["gdd_cumulative"] == 0.0


def test_candidate_rejects_nonfinite_gdd_even_when_lineage_exists():
    interpretation = {
        "field_id": "field-1",
        "season_id": "season-1",
        "recommendation_context": {
            "decision_boundary": {
                "is_decision": False,
                "consumer": "decision-service",
                "approval_required": True,
            }
        },
    }
    for bad in (float("nan"), float("inf"), -1.0, True):
        with pytest.raises(ValueError, match="finite and nonnegative"):
            build_crop_decision_candidate(
                interpretation,
                gdd_product={
                    "accumulated_gdd": bad,
                    "gdd_lineage_id": "gdd-1",
                    "contributing_state_ids": ["wx-1"],
                },
            )


def test_canonical_root_zone_supports_net_infiltration_screening():
    state = FieldTwinState("f1", {"depletion_mm": 70.0, "taw_mm": 100.0, "raw_mm": 45.0})
    out = simulate_irrigation(state, 20.0)
    assert out.predicted["depletion_mm_after_irrigation"] == 50.0
    assert out.predicted["root_zone_available_water_pct_after_irrigation"] == 50.0
    assert out.predicted["soil_moisture_pct_after_irrigation"] is None
    assert out.risks["water_stress"] == "medium"
    assert out.predicted["simulation_status"] == "screening_only_net_infiltration"
    assert any("no_execution_authority" in a for a in out.assumptions)


def test_percent_only_cannot_imply_depth_to_moisture_conversion():
    state = FieldTwinState("f1", {"soil_moisture_pct": 14.0})
    out = simulate_irrigation(state, 25.0)
    assert out.predicted["soil_moisture_pct_after_irrigation"] is None
    assert out.risks["water_stress"] == "unknown"
    assert out.predicted["simulation_status"] == "unavailable_without_canonical_root_zone"


@pytest.mark.parametrize("depth", [-1.0, float("nan"), float("inf"), True])
def test_invalid_irrigation_depth_fails_closed(depth):
    with pytest.raises(ValueError, match="finite nonnegative"):
        simulate_irrigation(FieldTwinState("f1", {"depletion_mm": 20.0, "taw_mm": 70.0}), depth)


def test_propose_ineligible_canonical_state_is_not_a_simulation_source():
    state = {
        "schema_version": "canonical_field_state.v1",
        "field_id": "f1",
        "season_id": "s1",
        "state_digest": "test-digest",
        "operational_eligible": True,  # presence-only, not fitness
        "eligibility": {"propose": {"allowed": False, "reasons": ["soil_owner_degraded"]}},
    }
    twin = build_field_twin_from_canonical_state(state)
    assert twin.risks["canonical_inputs"] == "unknown"
    assert "soil_owner_degraded" in twin.assumptions


def test_canonical_state_with_absent_required_products_never_promotes():
    twin = build_field_twin_from_canonical_state(
        {
            "schema_version": "canonical_field_state.v1",
            "field_id": "f1",
            "operational_eligible": False,
            "limitations": ["water_missing"],
        }
    )
    assert twin.risks["canonical_inputs"] == "unknown"
    assert "water_missing" in twin.assumptions


@pytest.mark.parametrize("value", [None, float("nan"), -1.0])
def test_missing_gdd_reports_no_nutrient_progress_anywhere(value):
    out = _crop({"accumulated_gdd": value, "series_quality_status": "insufficient"})
    assert out["nutrient"]["cumulative_fraction_to_date"] is None
    assert out["nutrient"]["stage"] is None
    nutrient_state = out["crop_intelligence"]["nutrient"]
    assert nutrient_state["cumulative_fraction_to_date"] is None
    assert nutrient_state["stage"] is None


@pytest.mark.parametrize(
    "series",
    [[10.0, None], [10.0, float("nan")], [10.0, -2.0], [10.0], []],
)
def test_compat_daily_gdd_with_a_gap_is_unavailable_not_summed(series):
    out = crop_twin_state(
        "wheat",
        [TwinDay(t_min_c=10, t_max_c=24, et0_mm=4, kc=1)] * 2,
        taw_mm=100,
        raw_fraction=0.5,
        gdd_daily_override=series,
    )
    assert out["phenology"]["status"] == "unavailable"
    assert out["phenology"]["gdd_cumulative"] is None


def test_compat_daily_gdd_complete_window_is_summed():
    out = crop_twin_state(
        "wheat",
        [TwinDay(t_min_c=10, t_max_c=24, et0_mm=4, kc=1)] * 2,
        taw_mm=100,
        raw_fraction=0.5,
        gdd_daily_override=[10.0, 0.0],
    )
    assert out["phenology"]["status"] == "available"
    assert out["phenology"]["gdd_cumulative"] == 10.0


@pytest.mark.parametrize(
    "eligibility",
    [None, {}, {"propose": {}}, {"propose": {"allowed": None}}, "garbage", {"propose": "yes"}],
)
def test_missing_or_malformed_propose_gate_fails_closed(eligibility):
    state = {
        "schema_version": "canonical_field_state.v1",
        "field_id": "f1",
        "operational_eligible": True,
        "water": {"depletion_mm": 10, "taw_mm": 100, "raw_mm": 50},
    }
    if eligibility is not None:
        state["eligibility"] = eligibility
    twin = build_field_twin_from_canonical_state(state)
    assert twin.risks["canonical_inputs"] == "unknown"
    assert "canonical_state_not_eligible_for_twin_simulation" in twin.assumptions


def test_field_twin_judges_dates_in_utc_and_rejects_nan_ndvi():
    from datetime import UTC, datetime, timedelta, timezone

    from core.field_twin import assemble_twin

    now = datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
    # 7 days 23 hours old in UTC is stale; written in +03:00 it must not read a day younger.
    old = (now - timedelta(days=7, hours=23)).astimezone(timezone(timedelta(hours=3)))
    twin = assemble_twin(
        field_id="f1",
        crop="wheat",
        latest_indices={"ndvi": 0.7},
        observed_at=old,
        index_observed_at={"ndvi": old},
        now=now,
        open_decisions=[],
        last_execution=None,
    )
    assert twin.data_age_days == 8 and twin.state == "stale"
    nan_twin = assemble_twin(
        field_id="f1",
        crop="wheat",
        latest_indices={"ndvi": float("nan")},
        observed_at=now,
        index_observed_at={"ndvi": now},
        now=now,
        open_decisions=[],
        last_execution=None,
    )
    assert nan_twin.state != "healthy" and nan_twin.ndvi is None
