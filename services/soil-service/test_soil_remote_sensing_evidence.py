from datetime import UTC, datetime

import pytest
from p2_products import build_bare_soil_composite, build_texture_probability

from shared.contracts.soil import (
    BareSoilCompositeRequest,
    BareSoilScene,
    TextureFeatureVector,
    TextureProbabilityRequest,
)


def soil_scene(scene_id, bands, moisture_proxy=0.1):
    return BareSoilScene(
        scene_id=scene_id,
        acquired_at=datetime(2026, 11, 1, tzinfo=UTC),
        band_means=bands,
        cloud_fraction=0.05,
        shadow_fraction=0.05,
        bare_fraction=0.8,
        vegetation_fraction=0.1,
        moisture_proxy=moisture_proxy,
    )


def composite(*scenes, **options):
    return build_bare_soil_composite(
        BareSoilCompositeRequest(
            tenant_id="t", field_id="f", geometry_hash="g", scenes=list(scenes), **options
        )
    )


def texture(**options):
    feature = TextureFeatureVector(zone_id="zone", **({"bare_bands": {}} | options))
    return build_texture_probability(
        TextureProbabilityRequest(
            tenant_id="t",
            field_id="f",
            geometry_hash="g",
            features=[feature],
        )
    )


@pytest.mark.parametrize("bands", [{}, {"red": float("nan")}, {"nir": float("inf")}])
def test_empty_or_invalid_scenes_do_not_create_evidence(bands):
    with pytest.raises(ValueError, match="no_eligible"):
        composite(soil_scene("bad", bands))


def test_duplicate_scene_does_not_inflate_confidence_or_band_support():
    first = soil_scene("a", {"red": 0.2})
    second = soil_scene("b", {"red": 0.4, "nir": 0.8}, moisture_proxy=0.9)
    product = composite(first, first, second)
    assert product.confidence_score == composite(first, second).confidence_score
    assert product.provenance["band_scene_ids"] == {"red": ["a", "b"], "nir": ["b"]}
    assert product.normalized_band_medians == {"red": 0.3, "nir": 0.8}
    with pytest.raises(ValueError, match="conflicting_duplicate"):
        composite(first, first.model_copy(update={"moisture_proxy": 0.9}))


def test_bad_thresholds_cannot_admit_clouds():
    with pytest.raises(ValueError, match="threshold"):
        composite(soil_scene("a", {"red": 0.2}), max_cloud_fraction=float("nan"))


@pytest.mark.parametrize(
    "options",
    [
        {"terrain": {"twi": 5}},
        {"bare_bands": {"red": 0.25}},
        {"bare_bands": {"red": 0.2, "swir1": 0.3, "swir2": 0.4, "nir": 0.5}},
        {"soilgrids": {"sand_pct": 40}},
        {"soilgrids": {"sand_pct": 80, "clay_pct": 50}},
        {"soilgrids": {"sand_pct": 40, "silt_pct": 40, "clay_pct": 40}},
        {"soilgrids": {"sand_pct": 40, "clay_pct": float("nan")}},
    ],
)
def test_unsupported_zones_get_no_particle_percentages(options):
    product = texture(**options)
    assert not product.zones
    assert product.provenance["texture_status"] == "insufficient_evidence"


def test_parent_fractions_are_not_changed_by_irrigation_or_spectral_features():
    base = texture(soilgrids={"clay_pct": 20, "sand_pct": 40})
    augmented = texture(
        soilgrids={"clay_pct": 20, "silt_pct": 40},
        terrain={"twi": 50},
        bare_bands={"swir1": 0.8, "red": 0.4},
    )
    assert base.zones == augmented.zones
    assert base.zones[0].texture_class == "loam"
    assert base.zones[0].uncertainty is None
    assert base.provenance["evidence_class"] == "modelled"
