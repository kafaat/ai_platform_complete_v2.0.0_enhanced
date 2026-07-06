"""Behavioural: terrain_render renders real tiles/contours from a synthetic DEM.

Not collected by the CI unit tier (testpaths = tests_v9); run locally with numpy/rasterio.
Proves the three layers actually produce output and fail closed without a DEM.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import rasterio
import terrain_render as tr
import tile_render
from PIL import Image
from rasterio.transform import from_origin


def _synthetic_dem(tmp_path: Path) -> tuple[str, list[float]]:
    lon0, lat0, n, res = 45.0, 15.5, 60, 0.0003  # ~30 m cells near Yemen
    xx, yy = np.meshgrid(np.arange(n), np.arange(n))
    dem = (1200.0 + yy * 3.0 + xx * 1.0).astype("float32")
    dem[0:3, 0:3] = -32768.0  # nodata sentinel corner
    aff = from_origin(lon0, lat0 + n * res, res, res)
    path = str(tmp_path / "dem.tif")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=n,
        width=n,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=aff,
        nodata=-32768,
    ) as ds:
        ds.write(dem, 1)
    return path, [lon0, lat0, lon0 + n * res, lat0 + n * res]


def test_hillshade_and_slope_tiles_render_opaque(tmp_path: Path):
    dem, bbox = _synthetic_dem(tmp_path)
    z = 15
    x, y = tile_render._lonlat_to_tile((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2, z)
    for render in (tr.render_hillshade_tile, tr.render_slope_tile):
        png = render(dem, z, x, y)
        assert png is not None
        alpha = np.array(Image.open(BytesIO(png)).convert("RGBA"))[..., 3]
        assert int((alpha > 0).sum()) > 0


def test_contours_produce_elevation_lines(tmp_path: Path):
    dem, bbox = _synthetic_dem(tmp_path)
    fc = tr.compute_field_contours(dem, bbox, interval_m=10.0)
    assert fc["computed"] is True and fc["source"] == "dem"
    assert len(fc["features"]) > 0
    for ft in fc["features"]:
        assert ft["geometry"]["type"] == "MultiLineString"
        assert isinstance(ft["properties"]["elevation_m"], (int, float))


def test_fail_closed_without_dem():
    assert tr.render_hillshade_tile("/nonexistent.tif", 15, 1, 1) is None
    assert tr.render_slope_tile("/nonexistent.tif", 15, 1, 1) is None
    fc = tr.compute_field_contours(None, [45.0, 15.5, 45.1, 15.6])
    assert fc["computed"] is False and fc["features"] == []
    assert fc["source"] == "dem-not-configured"
