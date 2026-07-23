from shared.gis.cloud_native_runtime import RasterRegistryRecord
from shared.gis.phase5_runtime import (
    STAC_CONFORMANCE,
    apply_undo_redo,
    build_scene_processing_plan,
    filter_records_for_stac,
    management_zone_summary,
    ogc_feature_collection,
    rank_scenes,
    stac_landing_page,
    stac_queryables,
    tile_cache_plan,
)


def _records():
    return [
        RasterRegistryRecord(
            id="1",
            tenant_id="t",
            field_id="f1",
            product_date="2026-06-20",
            index_type="ndvi",
            cog_url="s3://a.tif",
            cloud_pct=5,
            quality_score=90,
            bbox=[44, 15, 45, 16],
        ),
        RasterRegistryRecord(
            id="2",
            tenant_id="t",
            field_id="f1",
            product_date="2026-06-18",
            index_type="ndvi",
            cog_url="s3://b.tif",
            cloud_pct=60,
            quality_score=30,
            bbox=[44, 15, 45, 16],
        ),
        RasterRegistryRecord(
            id="3",
            tenant_id="t",
            field_id="f2",
            product_date="2026-06-19",
            index_type="truecolor",
            cog_url="s3://c.tif",
            cloud_pct=10,
            quality_score=80,
            bbox=[46, 15, 47, 16],
        ),
    ]


def test_stac_landing_and_queryables_are_complete():
    landing = stac_landing_page(api_base="https://api.example")
    assert "conformsTo" in landing and STAC_CONFORMANCE[0] in landing["conformsTo"]
    assert any(link["rel"] == "queryables" for link in landing["links"])
    assert "sahool:quality_score" in stac_queryables()["properties"]


def test_filter_rank_and_plan_scenes():
    filtered = filter_records_for_stac(_records(), field_id="f1", index_type="ndvi", max_cloud=40)
    assert [r.id for r in filtered] == ["1"]
    ranked = rank_scenes(_records())
    assert ranked[0]["scene_id"] == "1"
    plan = build_scene_processing_plan(_records(), field_id="f1", index_type="ndvi")
    assert plan["mosaic_ready"] is True
    assert "cache_warm" in plan["pipeline"]


def test_ogc_feature_collection_and_cache_plan():
    fc = ogc_feature_collection(
        [{"field_id": "f1", "name": "A", "geometry": {"type": "Point", "coordinates": [44, 15]}}]
    )
    assert fc["type"] == "FeatureCollection"
    assert fc["features"][0]["properties"]["name"] == "A"
    cache = tile_cache_plan(_records(), minzoom=8, maxzoom=10)
    assert cache["entries"][0]["ttl_seconds"] == 86400


def test_management_zones_and_undo_redo():
    zones = management_zone_summary([0.1, 0.2, 0.5, 0.7, 0.9, 1.0])
    assert len(zones["zones"]) == 3
    s = apply_undo_redo({"undo_stack": [], "redo_stack": []}, action="push", event={"op": "edit"})
    assert s["can_undo"] and not s["can_redo"]
    s = apply_undo_redo(s, action="undo")
    assert not s["can_undo"] and s["can_redo"]
    s = apply_undo_redo(s, action="redo")
    assert s["can_undo"] and not s["can_redo"]
