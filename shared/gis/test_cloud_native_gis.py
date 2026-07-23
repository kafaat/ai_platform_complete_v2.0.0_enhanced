from shared.gis.cloud_native_gis import (
    build_mosaicjson,
    geometry_revision_event,
    geoparquet_partition_path,
    normalize_stac_item,
    ogc_collection_descriptor,
    score_scene_quality,
)


def test_scene_quality_penalizes_clouds_and_accepts_clear_scene():
    clear = score_scene_quality(cloud_pct=2, shadow_pct=1, nodata_pct=0, resolution_m=10)
    cloudy = score_scene_quality(cloud_pct=70, shadow_pct=20, nodata_pct=10, resolution_m=30)
    assert clear.accepted is True
    assert clear.grade in {"A", "B"}
    assert cloudy.accepted is False
    assert cloudy.score < clear.score
    assert "cloud_pct" in cloudy.limiting_factors


def test_normalize_stac_item_extracts_cog_assets_and_quality():
    item = {
        "id": "S2A_001",
        "collection": "sentinel-2-l2a",
        "bbox": [44, 16, 45, 17],
        "properties": {"datetime": "2026-06-01T00:00:00Z", "eo:cloud_cover": 12},
        "assets": {
            "B04": {"href": "https://example/B04.tif", "type": "image/tiff; application=geotiff"},
            "metadata": {"href": "https://example/meta.json", "type": "application/json"},
        },
    }
    out = normalize_stac_item(item)
    assert out["scene_id"] == "S2A_001"
    assert out["cloud_pct"] == 12
    assert out["cog_assets"] == {"B04": "https://example/B04.tif"}
    assert out["quality"]["accepted"] is True


def test_build_mosaicjson_uses_scene_ids_as_stable_keys():
    mosaic = build_mosaicjson(
        name="field-season",
        items=[
            {
                "id": "scene-a",
                "collection": "sentinel-2-l2a",
                "properties": {"eo:cloud_cover": 4},
                "assets": {"visual": {"href": "s3://bucket/a.tif", "type": "image/tiff"}},
            }
        ],
    )
    assert mosaic["mosaicjson"] == "0.0.3"
    assert mosaic["tiles"] == {"scene-a": ["s3://bucket/a.tif"]}


def test_geoparquet_partition_path_is_lake_friendly():
    path = geoparquet_partition_path(
        country="Yemen", governorate="Al Jawf", district="Al Hazm", year=2026, crop="Wheat"
    )
    assert (
        path
        == "country=yemen/governorate=al-jawf/district=al-hazm/year=2026/crop=wheat/fields.geoparquet"
    )


def test_geometry_revision_event_rejects_unknown_operation():
    evt = geometry_revision_event(
        tenant_id="t1",
        field_id="f1",
        operation_type="split",
        geometry={"type": "Polygon", "coordinates": []},
        reason="new pivot sector",
    )
    assert evt["operation_type"] == "split"
    assert evt["source"] == "ui.map"


def test_ogc_collection_descriptor_links_items():
    desc = ogc_collection_descriptor(collection_id="fields", title="Fields", item_type="feature")
    assert desc["id"] == "fields"
    assert any(link["rel"] == "items" for link in desc["links"])
