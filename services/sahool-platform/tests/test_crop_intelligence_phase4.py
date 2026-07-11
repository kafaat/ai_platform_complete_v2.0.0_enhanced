import pytest
from core.crop_intelligence import (
    CropIntelligenceInput,
    build_crop_intelligence_state,
    build_crop_water_state,
)

pytestmark = pytest.mark.unit


def test_crop_water_requires_canonical_et0_and_versioned_kc_policy():
    out = build_crop_water_state(
        et0_mm=None,
        crop_coefficient=1.0,
        depletion_mm=40,
        raw_mm=50,
        root_depth_m=0.6,
        policy_version="wheat-kc/1.0.0",
    )
    assert out["status"] == "unavailable"
    assert out["crop_et_mm"] is None
    assert "et0_mm" in out["evidence_missing"]


def test_crop_water_interprets_upstream_et0_without_recomputing_it():
    out = build_crop_water_state(
        et0_mm=5.0,
        crop_coefficient=1.1,
        depletion_mm=45,
        raw_mm=50,
        root_depth_m=0.7,
        policy_version="wheat-kc/1.0.0",
        et0_method="fao56_penman_monteith",
        et0_quality_status="validated",
        source_ids=["weather:et0:1", "crop-policy:wheat:kc:1"],
    )
    assert out["status"] == "available"
    assert out["crop_et_mm"] == 5.5
    assert out["irrigation_urgency"] == "medium"
    assert out["ownership"]["et0"] == "weather-service"


def test_degraded_et0_propagates_quality_honestly():
    out = build_crop_water_state(
        et0_mm=5.0,
        crop_coefficient=1.0,
        depletion_mm=50,
        raw_mm=50,
        root_depth_m=0.7,
        policy_version="wheat-kc/1.0.0",
        et0_method="hargreaves_fallback",
        et0_quality_status="degraded",
    )
    assert out["status"] == "degraded"
    assert "upstream_et0_quality_is_degraded" in out["limitations"]


def test_canonical_crop_state_exposes_crop_water_and_non_decision_context():
    out = build_crop_intelligence_state(
        CropIntelligenceInput(
            crop="wheat",
            gdd_cumulative=600,
            gdd_to_maturity=1200,
            weather_state={
                "status": "available",
                "et0": {
                    "et0_mm": 6.0,
                    "method": "fao56_penman_monteith",
                    "quality_status": "validated",
                },
            },
            water_state={
                "status": "available",
                "depletion_mm": 55.0,
                "raw_mm": 50.0,
                "needs_irrigation": True,
            },
            root_policy={
                "initial_depth_m": 0.2,
                "maximum_depth_m": 1.2,
                "policy_version": "wheat-roots/1.0.0",
            },
            crop_water_policy={
                "crop_coefficient": 1.05,
                "policy_version": "wheat-kc/1.0.0",
            },
            source_ids=["weather:et0:1", "water:ledger:1"],
        )
    )
    assert out["engine_version"] == "crop-intelligence/5.0.0"
    assert out["crop_water"]["crop_et_mm"] == 6.3
    assert out["recommendation_context"]["urgency"] == "high"
    assert out["recommendation_context"]["decision_boundary"]["is_decision"] is False
    assert out["recommendation_context"]["decision_boundary"]["approval_required"] is True


def test_crop_twin_accepts_weather_and_crop_water_policy_without_new_route():
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
        crop_water_policy={
            "crop_coefficient": 0.8,
            "policy_version": "wheat-kc/1.0.0",
        },
        weather_state={
            "status": "available",
            "et0": {
                "et0_mm": 4.0,
                "method": "fao56_penman_monteith",
                "quality_status": "validated",
            },
        },
    )
    assert out["crop_intelligence"]["crop_water"]["status"] == "available"
