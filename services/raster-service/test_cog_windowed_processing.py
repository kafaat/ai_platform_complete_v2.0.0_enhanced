"""Bounded COG writes preserve pixel validity, geography and atomic publication."""

from types import SimpleNamespace

import cog_writer
import numpy as np
import pytest
import rasterio
from fastapi import HTTPException
from rasterio.transform import from_origin

pytestmark = pytest.mark.unit
TRANSFORM = from_origin(44, 16, 0.0001, 0.0001)


def _source(path, bands=3, crs="EPSG:4326", dtype="uint8"):
    data = np.full((bands, 530, 519), 90, dtype=dtype)
    if bands == 4:
        data[3] = 255
        data[3, 20:30, 30:40] = 0
    data[:, :10, :10] = 0
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=530,
        width=519,
        count=bands,
        dtype=dtype,
        crs=crs,
        transform=TRANSFORM,
        nodata=0,
    ) as dst:
        dst.write(data)
    return data


@pytest.mark.parametrize("kind", ["scalar", "rgb", "rgba"])
def test_array_masks_survive_external_mask_environment(tmp_path, kind):
    path = str(tmp_path / "result.tif")
    shape = (530, 519) if kind == "scalar" else (4 if kind == "rgba" else 3, 530, 519)
    array = np.ma.array(np.full(shape, 90, dtype="float32"), mask=np.zeros(shape, bool))
    array.mask[..., :10, :10] = True
    before = array.copy()
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=False):
        result = (
            cog_writer.write_cog(array, path, TRANSFORM)
            if kind == "scalar"
            else cog_writer.write_rgba_cog(array, path, TRANSFORM)
        )
    assert result["validation"]["valid"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["result.tif"]
    with rasterio.open(path) as src:
        assert src.dataset_mask()[0, 0] == 0
        assert src.dataset_mask()[20, 20] == 255
        assert src.transform == TRANSFORM
        assert src.crs.to_epsg() == 4326
    np.testing.assert_array_equal(array.data, before.data)
    np.testing.assert_array_equal(array.mask, before.mask)


@pytest.mark.parametrize("bands", [3, 4])
def test_open_source_uses_bounded_reads_and_preserves_nodata(tmp_path, monkeypatch, bands):
    source, output = tmp_path / "source.tif", tmp_path / "output.tif"
    _source(source, bands)
    reads = []
    for method in ("read", "dataset_mask"):
        original = getattr(rasterio.io.DatasetReader, method)

        def bounded(self, *args, _original=original, **kwargs):
            window = kwargs.get("window")
            assert window is not None, "full raster allocation"
            assert window.width <= 512 and window.height <= 512
            reads.append(window)
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(rasterio.io.DatasetReader, method, bounded)
    with rasterio.open(source) as src, rasterio.Env(GDAL_TIFF_INTERNAL_MASK=False):
        result = cog_writer.write_rgba_cog_source(src, str(output))
    assert result["validation"]["valid"]
    assert len(reads) >= 8
    monkeypatch.undo()
    with rasterio.open(output) as dst:
        assert dst.dataset_mask()[0, 0] == 0
        assert dst.dataset_mask()[100, 100] == 255
        assert dst.read(1)[100, 100] == 90
        if bands == 4:
            assert dst.dataset_mask()[25, 35] == 0
            assert dst.read(4)[25, 35] == 0


def test_interrupted_copy_keeps_previous_published_bytes(tmp_path, monkeypatch):
    source, output = tmp_path / "source.tif", tmp_path / "output.tif"
    _source(source)
    output.write_bytes(b"previous version")
    original = rasterio.io.DatasetReader.read
    calls = 0

    def fail(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected read failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(rasterio.io.DatasetReader, "read", fail)
    with rasterio.open(source) as src, pytest.raises(OSError, match="injected"):
        cog_writer.write_rgba_cog_source(src, str(output))
    assert output.read_bytes() == b"previous version"
    assert not list(tmp_path.glob(".cog-*"))


def _request(path):
    from raster_api_models import ProcessRequest

    return ProcessRequest(
        tenant_id="",
        field_id="f",
        raster_url=str(path),
        indicator="truecolor",
        source_format="sentinel2_l2a",
        bands={},
        provider="cdse",
        precomputed_index=True,
    )


@pytest.mark.parametrize("changes", [{"crs": None}, {"dtype": "uint16"}, {"bands": 2}])
def test_precomputed_invalid_metadata_rejected_before_pixel_read(tmp_path, monkeypatch, changes):
    import raster_pixel_processing as pp

    source = tmp_path / "source.tif"
    _source(source, **changes)
    for method in ("read", "dataset_mask"):

        def fail(*args, **kwargs):
            pytest.fail("invalid metadata must not reach pixel reads")

        monkeypatch.setattr(rasterio.io.DatasetReader, method, fail)
    ctx = SimpleNamespace(_safe_raster_source=lambda path: path, HTTPException=HTTPException)
    with pytest.raises(HTTPException) as exc:
        pp.process_precomputed_truecolor(ctx, _request(source))
    assert exc.value.status_code == 422


def test_precomputed_source_admission_precedes_pixel_reads(tmp_path, monkeypatch):
    import raster_pixel_processing as pp
    import raster_settings

    source = tmp_path / "source.tif"
    _source(source)
    monkeypatch.setattr(raster_settings, "RASTER_MAX_READ_BAND_PIXELS", 1)
    for method in ("read", "dataset_mask"):

        def fail(*args, **kwargs):
            pytest.fail("oversized source must not reach pixel reads")

        monkeypatch.setattr(rasterio.io.DatasetReader, method, fail)
    ctx = SimpleNamespace(_safe_raster_source=lambda path: path, HTTPException=HTTPException)
    with pytest.raises(HTTPException) as exc:
        pp.process_precomputed_truecolor(ctx, _request(source))
    assert exc.value.status_code == 413


def test_precomputed_statistics_and_output_use_same_open_source(tmp_path, monkeypatch):
    import raster_pixel_processing as pp

    source = tmp_path / "source.tif"
    _source(source)
    seen = []
    original = cog_writer.write_rgba_cog_source

    def capture(src, output):
        assert not src.closed
        seen.append(src)
        return original(src, output)

    monkeypatch.setattr(cog_writer, "write_rgba_cog_source", capture)
    ctx = SimpleNamespace(
        _safe_raster_source=lambda path: path,
        HTTPException=HTTPException,
        UPLOAD_DIR=str(tmp_path),
        object_store=SimpleNamespace(upload_cog=lambda *_: "stored"),
    )
    stats, _, _, meta = pp.process_precomputed_truecolor(ctx, _request(source))
    assert stats["valid_pixels"] == 530 * 519 - 100
    assert stats["nodata_pixels"] == 100
    assert stats["cog"]["validation"]["valid"]
    assert meta["cog_url"] == "stored"
    assert len(seen) == 1 and seen[0].closed
