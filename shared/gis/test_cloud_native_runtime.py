from pathlib import Path

from shared.gis.cloud_native_runtime import (
    record_from_db_row,
    stac_item_from_record,
    stac_collection,
    mosaicjson_from_records,
    tilejson_for_cog,
    export_records_to_geoparquet,
)


def _row(**overrides):
    base = {
        "id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "22222222-2222-2222-2222-222222222222",
        "field_id": "33333333-3333-3333-3333-333333333333",
        "scene_id": "S2A_TEST_20260601",
        "product_date": "2026-06-01",
        "index_type": "ndvi",
        "cog_url": "s3://sahool/ndvi.tif",
        "cloud_pct": 12,
        "quality_score": None,
        "resolution_m": 10,
        "bbox": [44, 15, 45, 16],
        "bands": {"b1": "ndvi"},
        "metadata": {"source": "test"},
    }
    base.update(overrides)
    return base


def test_record_stac_tilejson_are_db_backed_contracts():
    rec = record_from_db_row(_row())
    assert rec.quality_score is not None
    item = stac_item_from_record(rec)
    assert item["type"] == "Feature"
    assert item["assets"]["data"]["href"] == "s3://sahool/ndvi.tif"
    assert item["properties"]["sahool:field_id"] == "33333333-3333-3333-3333-333333333333"
    tilejson = tilejson_for_cog(rec, tiler_base_url="http://tiler")
    assert tilejson["tiles"][0].startswith("http://tiler/cog/tiles/WebMercatorQuad")
    assert "url=s3://sahool/ndvi.tif" in tilejson["tiles"][0]


def test_collection_and_mosaic_from_registry_records():
    records = [record_from_db_row(_row(scene_id="A", cog_url="/a.tif")), record_from_db_row(_row(scene_id="B", cog_url="/b.tif"))]
    coll = stac_collection(records, index_type="ndvi")
    assert coll["id"] == "sahool-ndvi"
    assert coll["extent"]["spatial"]["bbox"][0] == [44.0, 15.0, 45.0, 16.0]
    mosaic = mosaicjson_from_records(records, name="field-mosaic")
    assert mosaic["mosaicjson"] == "0.0.3"
    assert mosaic["tiles"] == {"A": ["/a.tif"], "B": ["/b.tif"]}


def test_geoparquet_export_has_deterministic_fallback(tmp_path: Path):
    result = export_records_to_geoparquet(
        [{"field_id": "f1", "geometry": {"type": "Point", "coordinates": [44, 15]}}],
        tmp_path / "fields.geoparquet",
    )
    assert result["rows"] == 1
    assert Path(result["path"]).exists()
    assert result["format"] in {"geoparquet", "jsonl-fallback"}
