"""Field denominator proof on exact affine cells; bounding boxes are not field geometry."""

from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from raster_field_coverage import for_published_asset, measure_field_coverage
from rasterio.transform import from_origin

pytestmark = pytest.mark.unit


def polygon(ring, *holes):
    return {"type": "Polygon", "coordinates": [ring, *holes]}


def rectangle(xmin, ymin, xmax, ymax):
    return [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)]


def raster(path, data, **profile):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=data.shape[0],
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=from_origin(0, 4, 1, 1),
        **profile,
    ) as src:
        src.write(data)
    return path


def test_partial_cog_hole_and_valid_zero(tmp_path):
    arr = np.zeros((1, 4, 4), dtype="float32")
    arr[0, 0, 0] = -9999
    arr[0, 2, 3] = np.nan
    path = raster(tmp_path / "coverage.tif", arr, nodata=-9999)
    # The last column belongs to the field but lies beyond the COG.
    geo = polygon(rectangle(0, 0, 5, 4), rectangle(1, 1, 2, 2))
    assert measure_field_coverage(path, geo, 3) == dict(
        denominator="field_pixel_centres",
        geometry_revision=3,
        field_pixels=19,
        valid_pixels=13,
        valid_pixel_ratio=13 / 19,
    )


def test_alpha_and_multipolygon(tmp_path):
    arr = np.full((4, 4, 4), 255, dtype="uint8")
    arr[3, 0, 0] = 0
    path = raster(tmp_path / "rgba.tif", arr)
    geo = {
        "type": "MultiPolygon",
        "coordinates": [
            [rectangle(0, 2, 2, 4)],
            [rectangle(3, 0, 4, 1)],
        ],
    }
    result = measure_field_coverage(path, geo, 1)
    assert (result["valid_pixels"], result["field_pixels"]) == (4, 5)


def test_missing_revision_subpixel_or_oversized_area_returns_unknown(tmp_path, monkeypatch):
    import raster_settings

    path = raster(tmp_path / "ndvi.tif", np.ones((1, 4, 4), dtype="float32"))
    assert measure_field_coverage(path, polygon(rectangle(0, 0, 1, 1)), None) is None
    assert measure_field_coverage(path, polygon(rectangle(0, 0, 0.1, 0.1)), 1) is None
    monkeypatch.setattr(raster_settings, "RASTER_MAX_READ_BAND_PIXELS", 10)
    assert measure_field_coverage(path, polygon(rectangle(0, 0, 4, 4)), 1) is None


@pytest.mark.asyncio
async def test_only_saved_boundary_can_supply_field_denominator(tmp_path, monkeypatch):
    import db_persist

    path = raster(tmp_path / "generic.tif", np.ones((1, 4, 4), dtype="float32"))
    req = SimpleNamespace(
        tenant_id="tenant",
        field_id="field",
        geometry_revision=None,
        clip_polygon_geojson=polygon(rectangle(0, 0, 1, 1)),
    )
    saved = {"geometry": polygon(rectangle(0, 0, 3, 3)), "revision": 2}

    async def snapshot(field, tenant):
        assert (field, tenant) == ("field", "tenant")
        return saved

    monkeypatch.setattr(db_persist, "fetch_field_geometry_with_revision", snapshot)
    stats = {"cog": {"path": path}}
    meta = {"spatial_sampling": {"output_pixel_size_m": [10, 10]}}
    result = await for_published_asset(req, stats, meta)
    assert result["field_pixels"] == 9
    req.geometry_revision = 1
    assert await for_published_asset(req, stats, meta) is None
    saved.clear()
    assert await for_published_asset(req, stats, meta) is None
