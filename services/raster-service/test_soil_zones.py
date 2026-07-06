"""Behavioural: soil field summary + sampling zones from a synthetic SoilGrids source.

Not collected by the CI unit tier (testpaths = tests_v9); run locally with numpy/rasterio.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import rasterio
import soil_render as s
import soil_zones as sz
from rasterio.transform import from_origin


def _synthetic_source(tmp_path: Path) -> list[float]:
    d = str(tmp_path)
    os.environ["SOILGRIDS_DIR"] = d
    lon0, lat0, n, res = 45.0, 15.5, 30, 0.002
    aff = from_origin(lon0, lat0 + n * res, res, res)

    def mk(prop: str, base: float, grad: float) -> None:
        arr = (base + np.tile(np.linspace(0, grad, n), (n, 1))).astype("float32")
        arr[0, 0] = -32768.0
        with rasterio.open(
            os.path.join(d, f"{prop}_0-5cm.tif"),
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

    mk("clay", 250, 200)  # stored ×10
    mk("sand", 400, -200)
    mk("phh2o", 70, 20)
    mk("soc", 150, 100)
    return [lon0, lat0, lon0 + n * res, lat0 + n * res]


def test_field_soil_summary(tmp_path: Path):
    bbox = _synthetic_source(tmp_path)
    r = s.compute_field_soil_summary(bbox)
    assert r["computed"] is True and r["source"] == "soilgrids"
    assert "clay" in r["properties"] and r["properties"]["clay"]["mean"] > 0
    assert r["texture_class"] is not None
    assert "disclaimer" in r


def test_soil_sampling_zones_polygonized(tmp_path: Path):
    bbox = _synthetic_source(tmp_path)
    z = sz.compute_soil_sampling_zones(bbox, n_zones=3)
    assert z["computed"] is True
    assert len(z["features"]) >= 2
    for f in z["features"]:
        assert f["geometry"]["type"] == "MultiPolygon"
        assert f["geometry"]["coordinates"]
        assert "soil" in f["properties"] and "zone_id" in f["properties"]


def test_soil_sampling_points_from_zone_centroids(tmp_path: Path):
    bbox = _synthetic_source(tmp_path)
    p = sz.compute_soil_sampling_points(bbox, n_zones=3, samples_per_zone=1)
    assert p["computed"] is True and p["source"] == "soilgrids-zone-centroids"
    assert len(p["features"]) >= 2
    for f in p["features"]:
        assert f["geometry"]["type"] == "Point"
        assert "point_id" in f["properties"] and "reason_ar" in f["properties"]
        assert f["properties"]["tests"]


def test_soil_summary_zones_fail_closed(monkeypatch):
    monkeypatch.delenv("SOILGRIDS_DIR", raising=False)
    assert s.compute_field_soil_summary([1, 2, 3, 4])["computed"] is False
    fc = sz.compute_soil_sampling_zones([1, 2, 3, 4])
    assert fc["computed"] is False and fc["features"] == []
    pts = sz.compute_soil_sampling_points([1, 2, 3, 4])
    assert pts["computed"] is False and pts["features"] == []
