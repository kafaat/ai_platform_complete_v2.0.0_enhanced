from pathlib import Path

import pytest

from shared.gis.cloud_native_runtime import (
    export_records_to_geoparquet,
    mosaicjson_from_records,
    record_from_db_row,
    stac_collection,
    stac_item_from_record,
    tilejson_for_cog,
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
    tilejson = tilejson_for_cog(rec)
    assert tilejson["tiles"] == [
        f"/api/v1/gis/cloud-native/rasters/{rec.id}/tiles/{{z}}/{{x}}/{{y}}.png?rescale=-1%2C1"
    ]
    assert rec.cog_url not in str(tilejson)


def test_collection_and_mosaic_from_registry_records():
    records = [
        record_from_db_row(_row(scene_id="A", cog_url="/a.tif")),
        record_from_db_row(_row(scene_id="B", cog_url="/b.tif")),
    ]
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


@pytest.mark.unit
@pytest.mark.parametrize("raw", [None, "", "n/a", float("nan"), -1, 101])
def test_unknown_registry_cloud_cover_stays_unknown_not_zero(raw):
    """G11 end-to-end: NULL/invalid DB cloud_pct is unknown (None), never a fabricated 0%."""
    rec = record_from_db_row(_row(cloud_pct=raw))
    assert rec.cloud_pct is None
    # 0% would score 100 (grade A); unknown is capped at 70 by score_scene_quality.
    assert rec.quality_score == 70
    props = stac_item_from_record(rec)["properties"]
    assert "eo:cloud_cover" not in props  # STAC eo:cloud_cover is a number; omit, not 0
    assert props["sahool:cloud_cover_known"] is False


@pytest.mark.unit
def test_known_registry_cloud_cover_including_real_zero_is_kept():
    clear = record_from_db_row(_row(cloud_pct=0))
    assert clear.cloud_pct == 0.0 and clear.quality_score == 100
    assert stac_item_from_record(clear)["properties"]["eo:cloud_cover"] == 0.0
    cloudy = record_from_db_row(_row(cloud_pct="12.5"))
    assert cloudy.cloud_pct == 12.5
    assert cloudy.quality_score == 84  # round(100 - 12.5 * 1.25) = round(84.375)
    props = stac_item_from_record(cloudy)["properties"]
    assert props["eo:cloud_cover"] == 12.5 and props["sahool:cloud_cover_known"] is True


@pytest.mark.unit
@pytest.mark.parametrize("raw", [None, "", "n/a", float("nan"), -1, 101])
def test_unknown_cloud_cover_caps_a_persisted_quality_score(raw):
    """A persisted score cannot outrank the unknown-cloud cap (review on #1329).

    Before: a row with unknown cover and a persisted ``quality_score=100`` kept 100, so
    it passed a STAC ``min_quality=85`` filter that the same row without a persisted
    score (capped at 70) fails. The cap now applies to the persisted value too.
    """
    from shared.gis.phase5_runtime import filter_records_for_stac

    rec = record_from_db_row(_row(cloud_pct=raw, quality_score=100))
    assert rec.cloud_pct is None
    assert rec.quality_score == 70
    assert filter_records_for_stac([rec], min_quality=85) == []
    assert stac_item_from_record(rec)["properties"]["sahool:quality_score"] == 70


@pytest.mark.unit
def test_unknown_cloud_cover_keeps_a_lower_persisted_score_and_known_cover_keeps_its_own():
    # A lower persisted score (e.g. shadow/no-data penalties) is kept, not raised to the cap.
    assert record_from_db_row(_row(cloud_pct=None, quality_score=40)).quality_score == 40
    assert record_from_db_row(_row(cloud_pct=None, quality_score="55")).quality_score == 55
    # Known cover: the persisted score is the registry's own judgement and stays as stored.
    assert record_from_db_row(_row(cloud_pct=12, quality_score=100)).quality_score == 100


@pytest.mark.unit
@pytest.mark.parametrize(
    "resolution", [None, 0, -1, float("nan"), float("inf"), "invalid", False, 7.5]
)
def test_registry_and_stac_preserve_only_measured_resolution(resolution):
    rec = record_from_db_row(_row(resolution_m=resolution))
    props = stac_item_from_record(rec)["properties"]
    if resolution == 7.5:
        assert rec.resolution_m == 7.5
        assert "gsd" not in props
    else:
        assert rec.resolution_m is None
        assert "gsd" not in props


@pytest.mark.unit
def test_stac_sampling_keeps_native_resolution_separate_from_output_grid():
    sampling = {
        "native_band_resolution_m": {"B11": 20},
        "output_pixel_size_m": [7.5, 8],
        "resampling_method": "bilinear",
    }
    record = record_from_db_row(_row(resolution_m=7.5, metadata={"spatial_sampling": sampling}))
    props = stac_item_from_record(record)["properties"]
    assert props["gsd"] == 20
    assert props["sahool:spatial_sampling"] == sampling


@pytest.mark.unit
def test_stac_mixed_native_bands_keep_per_band_values_without_single_gsd():
    sampling = {"native_band_resolution_m": {"nir": 10, "swir1": 20}, "output_pixel_size_m": [1, 1]}
    record = record_from_db_row(_row(resolution_m=1, metadata={"spatial_sampling": sampling}))
    props = stac_item_from_record(record)["properties"]
    assert "gsd" not in props
    assert props["sahool:spatial_sampling"] == sampling
