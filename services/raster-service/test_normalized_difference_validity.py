"""Normalized-difference indices must mask negative reflectance, not publish ±6e7 (G4).

Sentinel-2 L2A baseline >=04.00 applies BOA_ADD_OFFSET -1000 (-0.1 reflectance),
so dark/water pixels go below zero. With mixed signs the denominator reaches 0
and the epsilon guard used to emit -60,000,000; one such pixel corrupted the
published field mean. سالب الانعكاس ⇒ NaN خارج الإحصاء.
"""

import ast
import json
import math
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

import band_math
import numpy as np
import pytest

pytestmark = pytest.mark.unit


def test_audit_negative_reflectance_case_is_nodata():
    # The audit's measured pixel: RED=0.003, NIR=-0.003 → NIR+RED == 0 → -6e7.
    out = band_math.ndvi(np.array([0.003, 0.2]), np.array([-0.003, 0.6]), np)
    assert np.isnan(out[0])
    assert out[1] == pytest.approx(0.5)
    assert float(np.nanmean(out)) == pytest.approx(0.5)


@pytest.mark.parametrize(
    "fn",
    [
        lambda a, b: band_math.normalized_difference(a, b, np),
        lambda a, b: band_math.ndvi(b, a, np),
        lambda a, b: band_math.ndre(a, b, np),
        lambda a, b: band_math.moisture(a, b, np),
        lambda a, b: band_math.compute("ndre", {"nir": a, "rededge": b}, np),
        lambda a, b: band_math.compute("moisture", {"nir": a, "swir1": b}, np),
    ],
)
def test_every_band_math_normalized_difference_masks_invalid_inputs(fn):
    a = np.array([-0.003, 0.003, -0.05, 0.4, np.nan, 0.0, 0.6])
    b = np.array([0.003, -0.003, -0.02, -1e-6, 0.2, 0.0, 0.2])
    out = fn(a, b)
    assert np.isnan(out[:5]).all()  # any negative or nonfinite input band
    np.testing.assert_allclose(out[5:], [0.0, 0.5])  # legacy 0/0 contract kept
    finite = out[np.isfinite(out)]
    assert (np.abs(finite) <= 1.0).all()


def _run_process_pixels(tmp_path, indicator, band_attrs, *band_values):
    """Execute the real process_pixels on an N-band float32 GeoTIFF (no services).

    ``band_attrs[i]`` is read from file band i+1, whose first row starts with
    ``band_values[i]``; every other pixel is nodata.
    """
    import rasterio
    from rasterio.transform import from_origin

    source = Path(__file__).with_name("raster_pixel_processing.py")
    tree = ast.parse(source.read_text())
    functions = ast.Module(
        body=[n for n in tree.body if isinstance(n, ast.FunctionDef)], type_ignores=[]
    )
    scope = {
        "json": json,
        "math": math,
        "os": os,
        "uuid": uuid,
        "raw_data_processing": SimpleNamespace(
            compute_quality_score=lambda **kw: {"quality_score": 1},
            build_quality_flags=lambda **kw: [],
        ),
        "raster_validated_product": SimpleNamespace(
            build_validated_raster_product=lambda **kw: SimpleNamespace(model_dump=lambda **kw: {}),
            assert_indicator_accepts_validated_product=lambda product: None,
        ),
    }
    exec(compile(functions, str(source), "exec"), scope)
    scope["_topographic_qa_for_indicator"] = lambda *args, **kw: {"available": False}
    ctx = SimpleNamespace(
        _INDICATOR_FORMULAS={indicator: "test"},
        band_math=band_math,
        RASTER_NODATA=-9999.0,
        UPLOAD_DIR=str(tmp_path),
        object_store=SimpleNamespace(upload_cog=lambda path, key: Path(path).as_uri()),
        _quality_from_cloud_pct=lambda *a, **kw: {
            "confidence": 0,
            "quality": "unknown",
            "reason": "test",
        },
    )
    bands = dict.fromkeys(("red", "nir", "green", "blue", "swir1", "rededge", "swir2"), None)
    for file_band, attr in enumerate(band_attrs, start=1):
        bands[attr] = file_band
    req = SimpleNamespace(
        indicator=SimpleNamespace(value=indicator),
        bands=SimpleNamespace(**bands),
        clip_polygon_geojson=None,
        reflectance_scale=None,
        reflectance_offset=None,
        apply_cloud_mask=False,
        raw_qa_required=False,
        raster_url="fixture.tif",
        field_id=None,
    )
    data = np.full((len(band_values), 16, 16), -9999.0, dtype="float32")
    for i, values in enumerate(band_values):
        data[i, 0, : len(values)] = values
    path = tmp_path / "fixture.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=16,
        height=16,
        count=len(band_values),
        dtype="float32",
        nodata=-9999,
        crs="EPSG:32638",
        transform=from_origin(400000, 1772000, 10, 10),
    ) as dst:
        dst.write(data)
    old_errors = np.geterr()
    try:
        with rasterio.open(path) as src:
            stats, _, _, _ = scope["process_pixels"](ctx, req, "test", shared_src=src)
    finally:
        np.seterr(**old_errors)
    return stats


# (indicator, band read as file band 1, band read as file band 2). For each, the
# index is (band2 - band1) / (band2 + band1), so the ordinary pixel gives 0.5.
_RUNTIME_ND = [
    ("ndvi", ("red", "nir")),
    ("gndvi", ("green", "nir")),
    ("ndwi", ("nir", "green")),
    ("ndmi", ("swir1", "nir")),
    ("nbr", ("swir2", "nir")),
    ("ndre", ("rededge", "nir")),
    ("moisture", ("swir1", "nir")),
]


@pytest.mark.parametrize("indicator,band_attrs", _RUNTIME_ND)
def test_runtime_negative_reflectance_pixel_does_not_corrupt_published_mean(
    tmp_path, indicator, band_attrs
):
    # Pixel 0: audit case (band1=0.003, band2=-0.003). Pixel 1: ordinary 0.2/0.6.
    stats = _run_process_pixels(tmp_path, indicator, band_attrs, [0.003, 0.2], [-0.003, 0.6])
    assert stats["valid_pixels"] == 1
    assert stats["mean"] == pytest.approx(0.5, rel=1e-6)
    assert stats["min"] >= -1.0 and stats["max"] <= 1.0
