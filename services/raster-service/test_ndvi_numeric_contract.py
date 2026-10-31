"""NDVI arithmetic must not turn overflow or missing data into valid pixels."""

import ast
from pathlib import Path
from types import SimpleNamespace

import band_math
import numpy as np
import pytest


@pytest.mark.parametrize(
    "red,nir",
    [
        (np.array([40000], dtype="uint16"), np.array([50000], dtype="uint16")),
        (np.array([50000], dtype="uint16"), np.array([40000], dtype="uint16")),
        (np.array([2e38], dtype="float32"), np.array([3e38], dtype="float32")),
    ],
)
def test_ndvi_promotes_before_arithmetic(red, nir):
    # The oracle uses scalar Python float arithmetic, not NumPy's input dtype.
    expected = (float(nir[0]) - float(red[0])) / (float(nir[0]) + float(red[0]))
    np.testing.assert_allclose(band_math.ndvi(red, nir, np), [expected], rtol=1e-12)


def test_ndvi_float64_overflow_is_invalid_not_zero():
    out = band_math.ndvi(np.array([1e308]), np.array([1.5e308]), np)
    assert np.isnan(out[0])


def test_ndvi_nonfinite_and_zero_contract():
    out = band_math.ndvi(
        np.array([np.nan, np.inf, -np.inf, 0.0, 0.2]),
        np.array([0.4, 0.4, 0.4, 0.0, 0.6]),
        np,
    )
    assert np.isnan(out[:3]).all()
    np.testing.assert_allclose(out[3:], [0.0, 0.5])


def test_runtime_ndvi_branch_reuses_safe_arithmetic():
    # Execute the real NDVI branch without bootstrapping HTTP/DB services.
    source = Path(__file__).with_name("raster_pixel_processing.py")
    tree = ast.parse(source.read_text())
    branches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and ast.unparse(node.test) == "ind == 'ndvi'"
    ]
    assert len(branches) == 1
    program = ast.fix_missing_locations(ast.Module(body=branches[0].body, type_ignores=[]))
    red, nir = np.array([2e38], dtype="float32"), np.array([3e38], dtype="float32")
    scope = {
        "red": red,
        "nir": nir,
        "np": np,
        "ctx": SimpleNamespace(band_math=band_math),
    }
    exec(compile(program, str(source), "exec"), scope)
    expected = (float(nir[0]) - float(red[0])) / (float(nir[0]) + float(red[0]))
    np.testing.assert_allclose(scope["arr"], [expected], rtol=1e-12)


@pytest.mark.parametrize("indicator", ["ndvi", "fapar"])
@pytest.mark.parametrize("sample_case", ["large_finite", "positive_overflow", "negative_overflow"])
def test_process_pixels_reads_real_float32_raster(tmp_path, indicator, sample_case):
    """Execute processing and real COG writes; mock only service QA/object storage."""
    import json
    import math
    import os
    import uuid

    import rasterio
    from rasterio.transform import from_origin

    tree = ast.parse(Path(__file__).with_name("raster_pixel_processing.py").read_text())
    functions = ast.Module(
        body=[n for n in tree.body if isinstance(n, ast.FunctionDef)], type_ignores=[]
    )
    qa = SimpleNamespace(
        compute_quality_score=lambda **kw: {"quality_score": 1},
        build_quality_flags=lambda **kw: [],
    )
    validated = SimpleNamespace(
        build_validated_raster_product=lambda **kw: SimpleNamespace(model_dump=lambda **kw: {}),
        assert_indicator_accepts_validated_product=lambda product: None,
    )
    scope = {
        "json": json,
        "math": math,
        "os": os,
        "uuid": uuid,
        "raw_data_processing": qa,
        "raster_validated_product": validated,
    }
    exec(compile(functions, "raster_pixel_processing.py", "exec"), scope)
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
    req = SimpleNamespace(
        indicator=SimpleNamespace(value=indicator),
        bands=SimpleNamespace(
            red=1, nir=2, green=None, blue=None, swir1=None, rededge=None, swir2=None
        ),
        clip_polygon_geojson=None,
        reflectance_scale=None,
        reflectance_offset=None,
        apply_cloud_mask=False,
        raw_qa_required=False,
        raster_url="fixture.tif",
        field_id=None,
    )
    path = tmp_path / "fixture.tif"
    data = np.full((2, 16, 16), -9999.0, dtype="float32")
    data[:, 0, 1] = [0.2, 0.6]  # One ordinary pixel always survives.
    samples = {
        "large_finite": [2e38, 3e38],
        "positive_overflow": [-1e38, 1e38],
        "negative_overflow": [1e38, -1e38],
    }
    data[:, 0, 0] = samples[sample_case]
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=16,
        height=16,
        count=2,
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
    valid_indices = [1] if sample_case != "large_finite" else [0, 1]
    expected = np.array(
        [
            (float(data[1, 0, col]) - float(data[0, 0, col]))
            / (float(data[1, 0, col]) + float(data[0, 0, col]))
            for col in valid_indices
        ]
    )
    if indicator == "fapar":
        expected = np.clip(1.24 * expected - 0.168, 0, 1)
    assert stats["valid_pixels"] == len(valid_indices)
    assert stats["nodata_pixels"] == 256 - len(valid_indices)
    assert stats["mean"] == pytest.approx(float(expected.mean()), rel=1e-12)
    assert stats["cog"]["written"] is True
    with rasterio.open(stats["cog"]["path"]) as output:
        pixels = output.read(1, masked=True)
        assert pixels.count() == stats["valid_pixels"]
        assert bool(np.ma.getmaskarray(pixels)[0, 0]) == (sample_case != "large_finite")
        np.testing.assert_allclose(pixels.compressed(), expected.astype("float32"))
