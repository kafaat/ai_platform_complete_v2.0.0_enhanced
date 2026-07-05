"""Behavioural: soil_render renders a real SoilGrids property tile from a synthetic source.

Not collected by the CI unit tier (testpaths = tests_v9); run locally with numpy/rasterio.
Proves the soil layer renders colored tiles and fails closed without a configured source.
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

import numpy as np
import rasterio
import soil_render as s
import tile_render
from PIL import Image
from rasterio.transform import from_origin


def _synthetic_soilgrids(tmp_path: Path, prop: str = "phh2o") -> tuple[str, list[float]]:
    d = str(tmp_path)
    os.environ["SOILGRIDS_DIR"] = d
    lon0, lat0, n, res = 45.0, 15.5, 40, 0.002
    # pH stored ×10 (SoilGrids convention): 55..78 → pH 5.5..7.8; nodata corner.
    arr = (55.0 + np.arange(n)[None, :] * 0.5).astype("float32")
    arr = np.repeat(arr, n, axis=0)[:n]
    arr[0, 0] = -32768.0
    aff = from_origin(lon0, lat0 + n * res, res, res)
    path = os.path.join(d, f"{prop}_0-5cm.tif")
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
        ds.write(arr, 1)
    return path, [lon0, lat0, lon0 + n * res, lat0 + n * res]


def test_soil_tile_renders_colored(tmp_path: Path):
    _, bbox = _synthetic_soilgrids(tmp_path)
    z = 13
    x, y = tile_render._lonlat_to_tile((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2, z)
    png = s.render_soil_tile("phh2o", "0-5cm", z, x, y)
    assert png is not None
    rgba = np.array(Image.open(BytesIO(png)).convert("RGBA"))
    assert int((rgba[..., 3] > 0).sum()) > 0
    # a diverging pH ramp yields more than one colour across the value range.
    colours = {tuple(c) for c in rgba[rgba[..., 3] > 0][:, :3]}
    assert len(colours) > 1
    assert len(s.soil_legend("phh2o")) == 5


def test_soil_fail_closed_without_source(monkeypatch):
    monkeypatch.delenv("SOILGRIDS_DIR", raising=False)
    assert s.soil_raster_path("phh2o", "0-5cm") is None
    assert s.render_soil_tile("phh2o", "0-5cm", 13, 1, 1) is None
    assert s.is_source_configured() is False
