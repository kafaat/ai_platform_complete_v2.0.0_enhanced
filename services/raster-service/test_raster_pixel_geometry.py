"""Regression witnesses for output-grid geometry and terrain ground spacing.

PROC-02 — a field-clipped indicator/truecolor COG has its own (cropped) grid, so the
published ``bounds_4326`` (layer, validated product, registry bbox) must describe that
final grid, not the uncropped source scene.

PROC-03 — slope is a dimensionless rise/run ratio. When the indicator grid is in a
geographic CRS its spacing is in degrees, so terrain QA and the returned
``resolution_m`` must use ground metres per axis (x shrinks with cos(lat)), never the
raw degree value.

Synthetic rasters only (real rasterio/GDAL, no network, no provider, no DB).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

np = pytest.importorskip("numpy")
rasterio = pytest.importorskip("rasterio")
from rasterio.transform import array_bounds, from_origin  # noqa: E402
from rasterio.warp import transform_bounds  # noqa: E402

pytestmark = pytest.mark.unit

GEO_RES = 0.00027  # ~30 m at the equator (SRTM-like arc-second grid)
GEO_TRANSFORM = from_origin(44.0, 16.02, GEO_RES, GEO_RES)
UTM = "EPSG:32638"
UTM_TRANSFORM = from_origin(393000.0, 1773000.0, 10.0, 10.0)


def _write(path, *, crs, transform, bands, nodata=None):
    h, w = bands[0].shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=len(bands),
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        for i, band in enumerate(bands, start=1):
            dst.write(band.astype("float32"), i)


def _process(tmp_path, *, crs, transform, clip, indicator="ndvi", n=64):
    import raster_processing_runtime
    from raster_api_models import BandMapping, IndicatorKind, ProcessRequest, SourceFormat

    src = tmp_path / "scene.tif"
    red = np.full((n, n), 0.2)
    nir = np.full((n, n), 0.6)
    _write(src, crs=crs, transform=transform, bands=[red, nir, red, red])
    bands = (
        BandMapping(red=1, nir=2)
        if indicator == "ndvi"
        else BandMapping(red=1, nir=2, green=3, blue=4)
    )
    req = ProcessRequest(
        tenant_id="t_geom",
        field_id="field_geom",
        raster_url=f"file://{src}",
        indicator=IndicatorKind(indicator),
        source_format=SourceFormat.custom,
        bands=bands,
        clip_polygon_geojson=clip,
        apply_cloud_mask=False,
    )
    return raster_processing_runtime.process_pixels(req, "layer_geom", upload_dir=str(tmp_path))


def _cog_bounds_4326(meta):
    with rasterio.open(meta["cog_url"].replace("file://", "")) as cog:
        native = array_bounds(cog.height, cog.width, cog.transform)
        return list(transform_bounds(cog.crs, "EPSG:4326", *native)), cog.shape


def _box(minx, miny, maxx, maxy):
    return {
        "type": "Polygon",
        "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
    }


# ── PROC-02 ────────────────────────────────────────────────────────────────


def test_clipped_geographic_indicator_publishes_final_grid_bounds(tmp_path):
    stats, bounds, _res, meta = _process(
        tmp_path,
        crs="EPSG:4326",
        transform=GEO_TRANSFORM,
        clip=_box(44.004, 16.008, 44.009, 16.013),
    )
    cog_bounds, shape = _cog_bounds_4326(meta)
    assert shape != (64, 64), "witness must actually crop"
    assert bounds == pytest.approx(cog_bounds, abs=1e-9), (
        f"published bounds {bounds} != clipped COG grid bounds {cog_bounds}"
    )
    bbox = stats["validated_raster_product"]["spatial_bounds"]
    assert [bbox["minx"], bbox["miny"], bbox["maxx"], bbox["maxy"]] == pytest.approx(
        cog_bounds, abs=1e-9
    )


def test_clipped_projected_indicator_publishes_final_grid_bounds(tmp_path):
    full = transform_bounds(UTM, "EPSG:4326", *array_bounds(100, 100, UTM_TRANSFORM))
    dx, dy = full[2] - full[0], full[3] - full[1]
    clip = _box(full[0] + 0.3 * dx, full[1] + 0.3 * dy, full[0] + 0.6 * dx, full[1] + 0.6 * dy)
    _stats, bounds, res_m, meta = _process(
        tmp_path, crs=UTM, transform=UTM_TRANSFORM, clip=clip, n=100
    )
    cog_bounds, shape = _cog_bounds_4326(meta)
    assert shape != (100, 100)
    assert bounds == pytest.approx(cog_bounds, abs=1e-9)
    assert bounds[0] > full[0] + 0.25 * dx and bounds[2] < full[0] + 0.65 * dx
    # Projected metre grid: resolution is the native spacing, unchanged.
    assert res_m == pytest.approx(10.0)


def test_clipped_truecolor_publishes_final_grid_bounds(tmp_path):
    _stats, bounds, _res, meta = _process(
        tmp_path,
        crs="EPSG:4326",
        transform=GEO_TRANSFORM,
        clip=_box(44.004, 16.008, 44.009, 16.013),
        indicator="truecolor",
    )
    cog_bounds, shape = _cog_bounds_4326(meta)
    assert shape != (64, 64)
    assert bounds == pytest.approx(cog_bounds, abs=1e-9)


# ── PROC-03 ────────────────────────────────────────────────────────────────


def test_geographic_indicator_reports_ground_resolution_in_metres(tmp_path):
    _stats, _bounds, res_m, meta = _process(
        tmp_path,
        crs="EPSG:4326",
        transform=GEO_TRANSFORM,
        clip=_box(44.004, 16.008, 44.009, 16.013),
    )
    # 0.00027 deg of longitude at ~16.01 N on WGS84 ≈ 28.9 m (never 0.00027 "m").
    expected_x_m = GEO_RES * math.radians(1.0) * 6378137.0 * math.cos(math.radians(16.01))
    assert res_m == pytest.approx(expected_x_m, rel=5e-3)
    assert meta["resolution_m"] == pytest.approx(res_m)


def _dem_qa(tmp_path, monkeypatch, dem, *, crs, transform):
    import raster_pixel_processing as rpp

    path = tmp_path / "dem.tif"
    _write(path, crs=crs, transform=transform, bands=[dem])
    monkeypatch.setenv("FIELD_DEM_PATH", str(path))
    return rpp._topographic_qa_for_indicator(
        ctx=object(),
        req=None,
        raster_crs=crs,
        raster_transform=transform,
        raster_shape=dem.shape,
    )


def test_geographic_grid_slope_uses_ground_metres_not_degrees(tmp_path, monkeypatch):
    # +1 m per ~29 m pixel eastward ≈ 3.5 % slope: well under the 12 % risk threshold.
    dem = np.tile(np.arange(64, dtype="float32"), (64, 1))
    geo = _dem_qa(tmp_path, monkeypatch, dem, crs="EPSG:4326", transform=GEO_TRANSFORM)
    assert geo["slope_risk_pct"] == pytest.approx(0.0), geo
    # Same terrain on a ~30 m metric grid agrees.
    metric = _dem_qa(
        tmp_path, monkeypatch, dem, crs=UTM, transform=from_origin(393000.0, 1773000.0, 30, 30)
    )
    assert metric["slope_risk_pct"] == pytest.approx(0.0)


def test_geographic_grid_slope_is_anisotropic_with_latitude(tmp_path, monkeypatch):
    # 3.55 m per pixel: east-west spacing ≈ 28.9 m (12.3 % ≥ 12) but
    # north-south spacing ≈ 29.9 m (11.9 % < 12). A single isotropic spacing
    # cannot get both right.
    ramp = np.arange(64, dtype="float32") * 3.55
    east = _dem_qa(
        tmp_path, monkeypatch, np.tile(ramp, (64, 1)), crs="EPSG:4326", transform=GEO_TRANSFORM
    )
    north = _dem_qa(
        tmp_path,
        monkeypatch,
        np.tile(ramp[::-1, None], (1, 64)),
        crs="EPSG:4326",
        transform=GEO_TRANSFORM,
    )
    assert east["slope_risk_pct"] == pytest.approx(100.0), east
    assert north["slope_risk_pct"] == pytest.approx(0.0), north


def test_unknown_ground_spacing_fails_closed(tmp_path, monkeypatch):
    import raster_pixel_processing as rpp

    monkeypatch.setattr(rpp, "_ground_pixel_size_m", lambda *a, **k: None, raising=False)
    dem = np.tile(np.arange(64, dtype="float32"), (64, 1))
    out = _dem_qa(tmp_path, monkeypatch, dem, crs="EPSG:4326", transform=GEO_TRANSFORM)
    assert out["available"] is False
    assert out["slope_risk_pct"] is None
    assert out["fabricated_topographic_mask"] is False
    assert "raster_grid_ground_spacing_unknown" in out["warnings"]
