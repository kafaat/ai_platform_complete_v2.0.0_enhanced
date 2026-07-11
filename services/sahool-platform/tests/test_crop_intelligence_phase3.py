import pytest
from core.crop_intelligence import (
    CropIntelligenceInput,
    build_crop_intelligence_state,
    build_phenology_state,
    build_root_state,
    build_stress_memory,
)

pytestmark = pytest.mark.unit


def test_phenology_interprets_canonical_gdd_and_exposes_transition():
    out = build_phenology_state(
        gdd_cumulative=360,
        gdd_to_maturity=1200,
        method="canonical_weather_gdd",
        formula_version="gdd/1.0.0",
        source_ids=["weather:gdd:1"],
    )
    assert out["status"] == "available"
    assert out["current_stage"] == "development"
    assert out["previous_stage"] == "initial"
    assert out["next_stage"] == "mid"
    assert out["next_stage_gdd"] == 600.0


def test_phenology_is_fail_closed_without_canonical_gdd():
    out = build_phenology_state(
        gdd_cumulative=None,
        gdd_to_maturity=1200,
        method="canonical_weather_gdd",
        formula_version="gdd/1.0.0",
    )
    assert out["status"] == "unavailable"
    assert out["stage"] is None


def test_root_state_requires_explicit_versioned_policy():
    out = build_root_state(
        phenology_progress=0.5,
        initial_depth_m=None,
        maximum_depth_m=1.2,
        policy_version=None,
    )
    assert out["status"] == "unavailable"
    assert out["current_depth_m"] is None


def test_root_state_projects_only_from_explicit_policy():
    out = build_root_state(
        phenology_progress=0.5,
        initial_depth_m=0.2,
        maximum_depth_m=1.2,
        effective_fraction=0.8,
        policy_version="wheat-roots/1.0.0",
        source_ids=["crop-policy:wheat:1"],
    )
    assert out["status"] == "available"
    assert out["current_depth_m"] == 0.7
    assert out["effective_root_zone_m"] == 0.56


def test_stress_memory_is_unavailable_without_history():
    out = build_stress_memory(None)
    assert out["status"] == "unavailable"
    assert out["overall_burden"] is None


def test_stress_memory_uses_recency_and_reports_recovery():
    out = build_stress_memory(
        [
            {"type": "heat", "severity": 1.0},
            {"type": "heat", "severity": 0.9},
            {"type": "heat", "severity": 0.1},
        ],
        decay=0.85,
        source_ids=["weather:heat-history:1"],
    )
    assert out["status"] == "available"
    assert out["recovery_state"] == "recovering"
    assert out["observation_count"] == 3


def test_crop_state_v3_contains_phenology_roots_and_stress_memory():
    out = build_crop_intelligence_state(
        CropIntelligenceInput(
            crop="wheat",
            gdd_cumulative=600,
            gdd_to_maturity=1200,
            phenology_method="canonical_weather_gdd",
            phenology_formula_version="gdd/1.0.0",
            root_policy={
                "initial_depth_m": 0.2,
                "maximum_depth_m": 1.2,
                "policy_version": "wheat-roots/1.0.0",
            },
            stress_history=[{"type": "water", "severity": 0.7}],
            source_ids=["weather:gdd:1", "water:history:1"],
        )
    )
    assert out["schema"] == "crop_intelligence_state.v2"
    assert out["phenology"]["stage"] == "development"
    assert out["root_state"]["status"] == "available"
    assert out["stress_memory"]["status"] == "available"


def test_no_biomass_or_yield_fabrication_in_v3():
    out = build_crop_intelligence_state(
        CropIntelligenceInput(crop="wheat", gdd_cumulative=100, gdd_to_maturity=1200)
    )
    assert out["biomass"]["status"] == "unavailable"
    assert out["yield_projection"]["status"] == "unavailable"


def test_crop_twin_passes_optional_root_policy_and_stress_history():
    from api.crop_twin import TwinDay, crop_twin_state

    out = crop_twin_state(
        "wheat",
        [TwinDay(t_min_c=10, t_max_c=20, et0_mm=4, kc=0.8)],
        taw_mm=100,
        raw_fraction=0.5,
        root_policy={
            "initial_depth_m": 0.2,
            "maximum_depth_m": 1.2,
            "policy_version": "wheat-roots/1.0.0",
        },
        stress_history=[{"type": "water", "severity": 0.6}],
    )
    assert out["crop_intelligence"]["root_state"]["status"] == "available"
    assert out["crop_intelligence"]["stress_memory"]["status"] == "available"
