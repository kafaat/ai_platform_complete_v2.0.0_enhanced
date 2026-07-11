import pytest
from core.crop_intelligence import CropIntelligenceInput, build_crop_intelligence_state

pytestmark = pytest.mark.unit


def test_builds_phenology_without_recomputing_weather():
    out = build_crop_intelligence_state(
        CropIntelligenceInput(
            crop="wheat",
            gdd_cumulative=600,
            gdd_to_maturity=1200,
            phenology_method="canonical_weather_gdd",
            phenology_formula_version="gdd/1.0.0",
            water_state={"needs_irrigation": False, "status": "available"},
            source_ids=["weather:gdd:1"],
        )
    )
    assert out["phenology"]["progress"] == 0.5
    assert out["phenology"]["method"] == "canonical_weather_gdd"
    assert out["evidence_ids"] == ["weather:gdd:1"]


def test_missing_gdd_is_fail_closed():
    out = build_crop_intelligence_state(
        CropIntelligenceInput(crop="wheat", gdd_cumulative=None, gdd_to_maturity=1200)
    )
    assert out["phenology"]["stage"] is None
    assert "gdd_cumulative" in out["evidence_missing"]
    assert out["confidence"] == "low"


def test_does_not_fabricate_biomass_or_yield():
    out = build_crop_intelligence_state(
        CropIntelligenceInput(crop="wheat", gdd_cumulative=100, gdd_to_maturity=1200)
    )
    assert out["biomass"]["status"] == "unavailable"
    assert out["yield_projection"]["status"] == "unavailable"


def test_combines_only_explicit_stress_evidence():
    out = build_crop_intelligence_state(
        CropIntelligenceInput(
            crop="wheat",
            gdd_cumulative=100,
            gdd_to_maturity=1200,
            water_state={"needs_irrigation": True},
            vegetation_state={"water_stress_confirmed": True},
            weather_state={"heat_stress": True},
        )
    )
    assert {x["code"] for x in out["stress_flags"]} == {
        "water_deficit",
        "spectral_water_stress",
        "heat_stress",
    }


def test_unknown_crop_is_explicitly_limited():
    out = build_crop_intelligence_state(
        CropIntelligenceInput(crop="unknown-x", gdd_cumulative=100, gdd_to_maturity=1000)
    )
    assert out["crop_known"] is False
    assert "unknown_crop_uses_generic_crop_identity" in out["limitations"]
