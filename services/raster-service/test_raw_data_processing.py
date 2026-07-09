from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

import raw_data_processing

pytestmark = pytest.mark.unit


def test_raw_data_processing_reports_band_stats_and_provenance(tmp_path):
    raster_path = tmp_path / "raw_scene.tif"
    arr1 = np.array([[1000, 2000], [0, 4000]], dtype=np.uint16)
    arr2 = np.array([[10, 20], [30, 40]], dtype=np.uint16)
    transform = from_origin(44.0, 16.0, 10.0, 10.0)
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=2,
        dtype="uint16",
        crs="EPSG:4326",
        transform=transform,
        nodata=0,
    ) as dst:
        dst.write(arr1, 1)
        dst.write(arr2, 2)

    ctx = SimpleNamespace(
        _safe_raster_source=lambda url: url.replace("file://", ""),
        band_math=SimpleNamespace(to_reflectance=lambda a, scale, offset, np_mod: a * 0.0001),
    )
    req = SimpleNamespace(
        tenant_id="tenant_a",
        field_id="field_a",
        raster_url=f"file://{raster_path}",
        bands=[1],
        normalize_reflectance=True,
        include_tags=False,
        max_pixels=10000,
    )

    out = raw_data_processing.process_raw_raster(ctx, req)

    assert out["schema"] == "sahool.raw_raster_processing/1"
    assert out["provenance"]["fabricated_indicator"] is False
    assert out["provenance"]["indicator_computed"] is False
    assert out["source"]["count"] == 2
    assert len(out["raw_bands"]) == 1
    assert out["raw_bands"][0]["index"] == 1
    assert out["raw_bands"][0]["raw_stats"]["valid_pixels"] == 3
    assert out["raw_bands"][0]["raw_stats"]["nodata_pixels"] == 1
    assert len(out["normalized_bands"]) == 1
    assert out["normalized_bands"][0]["reflectance_stats"]["max"] == pytest.approx(0.4)


def test_raw_data_processing_rejects_out_of_range_band(tmp_path):
    raster_path = tmp_path / "raw_scene.tif"
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        height=1,
        width=1,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(44.0, 16.0, 10.0, 10.0),
    ) as dst:
        dst.write(np.array([[1]], dtype=np.uint8), 1)

    ctx = SimpleNamespace(_safe_raster_source=lambda url: url.replace("file://", ""))
    req = SimpleNamespace(
        tenant_id="tenant_a",
        field_id=None,
        raster_url=f"file://{raster_path}",
        bands=[2],
        normalize_reflectance=False,
        include_tags=False,
        max_pixels=10000,
    )

    with pytest.raises(ValueError, match="band index 2"):
        raw_data_processing.process_raw_raster(ctx, req)
