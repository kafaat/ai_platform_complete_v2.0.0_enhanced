from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sahool_platform_path import ensure_platform_path

pytestmark = pytest.mark.unit
ensure_platform_path()

from api.canonical_salinity_state import (  # noqa: E402
    CropSalinityTolerance,
    DrainageEvidence,
    SoilSalinityEvidence,
    WaterQualityEvidence,
    build_canonical_salinity_state,
)

NOW = datetime(2026, 8, 3, 1, tzinfo=UTC)
D1, D2, D3, D4 = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)


def soil(ece=3.0, days=10):
    return SoilSalinityEvidence(ece, NOW - timedelta(days=days), D1, 30)


def water(ecw=1.2, *, sar=8, rsc=1.0, chloride=None, boron=None, days=10):
    return WaterQualityEvidence(ecw, NOW - timedelta(days=days), D2, sar, rsc, chloride, boron)


def drainage(kind="good", days=20):
    return DrainageEvidence(kind, NOW - timedelta(days=days), D3, 2.0)


def tolerance(threshold=4.0, decline=7.1, factor=1.0, **extra):
    return CropSalinityTolerance(threshold, decline, D4, factor, **extra)


def build(**overrides):
    args = dict(
        tenant_id="t1",
        field_id="f1",
        season_id="s1",
        crop_id="wheat",
        cultivar_id="bahouth-3",
        phenology_stage="development",
        as_of=NOW,
        soil=soil(),
        water=water(),
        drainage=drainage(),
        tolerance=tolerance(),
    )
    args.update(overrides)
    return build_canonical_salinity_state(**args)


def test_managed_state_combines_all_evidence():
    state = build()
    assert state.status == "managed"
    assert state.operational_recommendation_allowed is True
    assert state.soil_class == "slightly_saline"
    assert state.water_risk == "slight_moderate"
    assert state.sodium_hazard_class == "low"
    assert state.rsc_hazard_class == "low"
    assert state.estimated_relative_yield == 1.0
    assert state.leaching_fraction is not None
    assert len(state.evidence_digests) == 4


def test_poor_drainage_blocks_leaching_recommendation():
    state = build(drainage=drainage("poor"))
    assert state.status == "blocked"
    assert state.operational_recommendation_allowed is False
    assert "POOR_DRAINAGE_BLOCKS_LEACHING" in state.limitations


def test_missing_tolerance_does_not_fabricate_crop_suitability():
    state = build(tolerance=None)
    assert state.status == "blocked"
    assert state.effective_crop_threshold_ece_dsm is None
    assert state.estimated_relative_yield is None
    assert "MISSING_CROP_SALINITY_TOLERANCE" in state.limitations


def test_stale_water_blocks_operational_recommendation():
    state = build(water=water(days=500))
    assert state.status == "blocked"
    assert "STALE_IRRIGATION_WATER_QUALITY" in state.limitations


def test_high_risk_preserves_quantitative_result():
    state = build(soil=soil(10), water=water(3.5, sar=22, rsc=3.0))
    assert state.status == "high_risk"
    assert state.estimated_relative_yield < 1
    assert state.sodium_hazard_class == "high"
    assert state.rsc_hazard_class == "high"


def test_chloride_and_boron_require_crop_specific_thresholds():
    state = build(water=water(chloride=500, boron=2))
    assert "CHLORIDE_THRESHOLD_UNAVAILABLE" in state.limitations
    assert "BORON_THRESHOLD_UNAVAILABLE" in state.limitations
    guarded = build(
        water=water(chloride=500, boron=2),
        tolerance=tolerance(chloride_threshold_mg_l=300, boron_threshold_mg_l=1),
    )
    assert "CHLORIDE_EXCEEDS_CROP_THRESHOLD" in guarded.limitations
    assert "BORON_EXCEEDS_CROP_THRESHOLD" in guarded.limitations
    assert guarded.status == "high_risk"


def test_stage_factor_changes_effective_threshold_without_hidden_defaults():
    state = build(tolerance=tolerance(factor=0.8), soil=soil(3.5))
    assert state.effective_crop_threshold_ece_dsm == pytest.approx(3.2)
    assert state.estimated_relative_yield < 1
    fallback = build(tolerance=tolerance(factor=None))
    assert "STAGE_SPECIFIC_TOLERANCE_UNAVAILABLE" in fallback.limitations


def test_deterministic_digest_and_validation():
    assert build().state_digest == build().state_digest
    with pytest.raises(ValueError, match="timezone-aware"):
        build(as_of=datetime(2026, 8, 3, 1))
    with pytest.raises(ValueError, match="finite and non-negative"):
        build(soil=soil(float("nan")))
    with pytest.raises(ValueError, match="unknown drainage_class"):
        build(drainage=drainage("invented"))
