from datetime import UTC, datetime

import pytest
from p2_products import (
    build_bare_soil_composite,
    build_salinity_assessment,
    build_terrain_derivatives,
    build_texture_probability,
)

from shared.contracts.soil import (
    BareSoilCompositeRequest,
    BareSoilScene,
    SalinityAssessmentRequest,
    SalinityZoneEvidence,
    TerrainRequest,
    TextureFeatureVector,
    TextureProbabilityRequest,
)


def test_bare_soil_filters_and_normalizes():
    req = BareSoilCompositeRequest(
        tenant_id="t",
        field_id="f",
        geometry_hash="g",
        scenes=[
            BareSoilScene(
                scene_id="ok1",
                acquired_at=datetime.now(UTC),
                cloud_fraction=0.05,
                shadow_fraction=0.02,
                vegetation_fraction=0.1,
                bare_fraction=0.8,
                moisture_proxy=0.3,
                band_means={"red": 0.2, "nir": 0.3},
            ),
            BareSoilScene(
                scene_id="ok2",
                acquired_at=datetime.now(UTC),
                cloud_fraction=0.1,
                shadow_fraction=0.03,
                vegetation_fraction=0.15,
                bare_fraction=0.7,
                moisture_proxy=0.5,
                band_means={"red": 0.24, "nir": 0.31},
            ),
            BareSoilScene(
                scene_id="bad",
                acquired_at=datetime.now(UTC),
                cloud_fraction=0.8,
                shadow_fraction=0.0,
                vegetation_fraction=0.0,
                bare_fraction=0.8,
                moisture_proxy=0.2,
                band_means={"red": 0.5},
            ),
        ],
    )
    p = build_bare_soil_composite(req)
    assert p.selected_scene_ids == ["ok1", "ok2"]
    assert "bad" in p.rejected_scenes
    assert 0 < p.confidence_score <= 1


def test_bare_soil_fails_without_eligible_scene():
    req = BareSoilCompositeRequest(
        tenant_id="t",
        field_id="f",
        geometry_hash="g",
        scenes=[
            BareSoilScene(
                scene_id="x",
                acquired_at=datetime.now(UTC),
                cloud_fraction=0.9,
                shadow_fraction=0.2,
                vegetation_fraction=0.4,
                bare_fraction=0.1,
                moisture_proxy=0.2,
                band_means={"red": 0.2},
            )
        ],
    )
    with pytest.raises(ValueError, match="no_eligible"):
        build_bare_soil_composite(req)


def test_terrain_outputs_all_required_derivatives():
    dem = [[10, 11, 12, 13], [9, 10, 11, 12], [8, 9, 8, 11], [7, 8, 9, 10]]
    p = build_terrain_derivatives(
        TerrainRequest(
            tenant_id="t",
            field_id="f",
            geometry_hash="g",
            dem_version="glo30",
            cell_size_m=30,
            elevation_m=dem,
        )
    )
    required = {
        "slope_deg",
        "tpi",
        "twi",
        "plan_curvature",
        "profile_curvature",
        "flow_accumulation",
        "relative_elevation",
        "wadi_distance_m",
    }
    assert required <= set(p.summaries)
    assert sum(p.landform_counts.values()) == 4


def test_texture_is_modelled_and_spatial_cv_fail_closed_without_samples():
    req = TextureProbabilityRequest(
        tenant_id="t",
        field_id="f",
        geometry_hash="g",
        features=[
            TextureFeatureVector(
                zone_id="z1",
                bare_bands={"red": 0.2, "nir": 0.3, "swir1": 0.25, "swir2": 0.28},
                terrain={"twi": 7},
                soilgrids={"clay_pct": 35, "sand_pct": 40},
            )
        ],
    )
    p = build_texture_probability(req)
    z = p.zones[0]
    assert abs(z.estimated_clay_pct + z.estimated_sand_pct + z.estimated_silt_pct - 100) < 0.01
    assert p.spatial_cv["status"] == "insufficient_local_samples"
    assert p.provenance["evidence_class"] == "modelled"


def test_salinity_screening_blocks_high_risk_and_lab_verified_allows():
    req = SalinityAssessmentRequest(
        tenant_id="t",
        field_id="f",
        geometry_hash="g",
        zones=[
            SalinityZoneEvidence(
                zone_id="screen",
                salinity_index=0.8,
                brightness=0.7,
                gypsum_index=0.2,
                carbonate_index=0.2,
                persistence=0.8,
                drainage_risk=0.8,
            ),
            SalinityZoneEvidence(
                zone_id="lab",
                salinity_index=0.8,
                brightness=0.7,
                gypsum_index=0.2,
                carbonate_index=0.2,
                persistence=0.8,
                drainage_risk=0.8,
                ec_lab_ds_m=6,
                esp_pct=18,
                sar=20,
                ecw_ds_m=2,
            ),
        ],
    )
    p = build_salinity_assessment(req)
    assert "gypsum_rate" in p.zones[0].blocked_use
    assert p.zones[1].evidence_level == "lab_verified"
    assert p.zones[1].blocked_use == []
    assert p.zones[1].classification == "saline_sodic"
