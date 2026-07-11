import pytest
from core.crop_intelligence import (
    CropIntelligenceInput,
    build_canonical_spectral_state,
    build_crop_intelligence_state,
)

pytestmark = pytest.mark.unit


def test_spectral_state_confirms_water_stress_from_temporally_compatible_ndmi_msi():
    spectral = build_canonical_spectral_state(
        ndmi=-0.1,
        msi=2.2,
        temporal_compatible=True,
        product_ids=["raster:ndmi:1", "raster:msi:1"],
        quality_status="validated",
    )
    assert spectral["schema"] == "canonical_spectral_state.v1"
    assert spectral["water_stress"]["confirmation_available"] is True
    assert spectral["water_stress"]["confirmed"] is True
    assert spectral["evidence_ids"] == ["raster:ndmi:1", "raster:msi:1"]


def test_spectral_state_fails_closed_without_temporal_compatibility():
    spectral = build_canonical_spectral_state(
        ndmi=-0.1,
        msi=2.2,
        temporal_compatible=False,
    )
    assert spectral["water_stress"]["confirmation_available"] is False
    assert spectral["water_stress"]["confirmed"] is None
    assert "ndmi_msi_temporal_compatibility_not_verified" in spectral["limitations"]


def test_non_finite_spectral_values_are_missing_not_severe():
    spectral = build_canonical_spectral_state(
        ndmi=float("nan"),
        msi=float("inf"),
        temporal_compatible=True,
    )
    assert spectral["indices"]["ndmi"] is None
    assert spectral["indices"]["msi"] is None
    assert spectral["water_stress"]["confirmed"] is None


def test_crop_state_consumes_spectral_product_without_recomputing_indices():
    spectral = build_canonical_spectral_state(
        ndmi=-0.2,
        msi=2.3,
        temporal_compatible=True,
        product_ids=["ndmi-product", "msi-product"],
    )
    out = build_crop_intelligence_state(
        CropIntelligenceInput(
            field_id="fld-1",
            season_id="season-1",
            crop="wheat",
            gdd_cumulative=600,
            gdd_to_maturity=1200,
            spectral_state=spectral,
            source_ids=spectral["evidence_ids"],
        )
    )
    assert out["schema"] == "crop_intelligence_state.v2"
    assert out["field_id"] == "fld-1"
    assert out["season_id"] == "season-1"
    assert {x["code"] for x in out["stress_flags"]} == {"spectral_water_stress"}
    assert out["spectral"]["ownership"]["index_computation"] == "raster-service"
