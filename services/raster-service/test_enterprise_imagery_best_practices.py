import main
from fastapi.testclient import TestClient


def test_scene_ranking_prefers_aoi_low_cloud_over_latest_cloudy():
    scenes = [
        {
            "item_id": "new-cloudy",
            "datetime": "2026-06-20T00:00:00Z",
            "cloud_cover_pct": 80,
            "aoi_cloud_pct": 75,
            "coverage_pct": 100,
        },
        {
            "item_id": "older-clear",
            "datetime": "2026-06-01T00:00:00Z",
            "cloud_cover_pct": 5,
            "aoi_cloud_pct": 2,
            "coverage_pct": 95,
        },
    ]
    ranked = main._rank_scenes(scenes, max_cloud_pct=40, prefer_recent_days=60)
    assert ranked[0]["item_id"] == "older-clear"
    assert ranked[0]["sahool_quality"]["cloud_source"] == "aoi_cloud_pct"


def test_band_mapping_supports_s2cloudless_quality_bands():
    bands = main.BandMapping(red=1, nir=2, scl=3, clp=4, clm=5)
    assert bands.clp == 4
    assert bands.clm == 5


def test_tile_cache_key_is_tenant_scoped_and_safe():
    key = main._tile_cache_key("fld/../1", "NDVI", "latest", 12, 345, 678, "tenant/../A")
    assert "tile_cache" in key
    assert ".." not in key
    assert "tenant" in key
    assert key.endswith("345_678.png")


def test_quality_policy_endpoint_exposes_enterprise_rules():
    client = TestClient(main.app)
    resp = client.get("/v1/imagery/quality/policy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cloud_mask"]["preferred"] == ["CLM", "CLP", "SCL"]
    assert data["scene_ranking"]["weights"]["cloud"] == 0.5
    assert data["geometry_history"]["table"] == "field_geometry_versions"


def test_scene_rank_endpoint_returns_best_scene():
    client = TestClient(main.app)
    resp = client.post(
        "/v1/imagery/scenes/rank",
        json={
            "max_cloud_pct": 40,
            "scenes": [
                {"item_id": "bad", "datetime": "2026-06-20T00:00:00Z", "aoi_cloud_pct": 90},
                {"item_id": "good", "datetime": "2026-06-10T00:00:00Z", "aoi_cloud_pct": 3},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["best_scene"]["item_id"] == "good"
