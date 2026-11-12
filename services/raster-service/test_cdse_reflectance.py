"""Synthetic provider returns exercise the actual HTTP payload, TIFF and metadata paths."""

import io
import json
import tarfile

import cdse_client
import cdse_native_product as native
import httpx
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

pytestmark = pytest.mark.unit
BBOX = [44, 15, 44.0004, 15.0004]  # ~43 x 45 m: 4x4 working samples -> 2x2 output


def provider(payload, index, quality, *, invalid_mask=False, mixed=False):
    w, h = (payload["output"][key] for key in ("width", "height"))
    assert (w, h) == (4, 4)
    order = cdse_client.INDEX_EXPR[index][0]
    array = np.ones((len(order) + 3, h, w), dtype="float32")
    values = {"B02": 0.05, "B04": 0.15, "B05": 0.2, "B11": 0.2, "B12": 0.3}
    for i, band in enumerate(order):
        if band != "B08":
            array[i] = values[band]
    array[order.index("B08")] = np.tile([[0.1, 0.9], [0.1, 0.9]], (2, 2))
    array[-3] = 4
    array[-3, 0, 0] = 9
    array[-2:, 2, 0] = 0
    array[-3, 2, 2] = 1
    if invalid_mask:
        array[-2, 0, 3] = 2
    if mixed:
        array[-1, 0, 3] = 2
    with rasterio.MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=w,
            height=h,
            count=len(array),
            dtype="float32",
            crs="EPSG:4326",
            transform=from_bounds(*BBOX, w, h),
        ) as dst:
            dst.write(array)
        tiff = mem.read()
    if not quality:
        return tiff
    out = io.BytesIO()
    metadata = {"schema": native.SCHEMA, "tiles": [{"id": "42", "date": "2026-10-01T00:00:00Z"}]}
    with tarfile.open(fileobj=out, mode="w") as tar:
        for name, data in (("default.tif", tiff), ("userdata.json", json.dumps(metadata).encode())):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return out.getvalue()


@pytest.mark.parametrize(
    "index,expected",
    [
        ("ndmi", 3 / 7),
        ("ndre", 3 / 7),
        ("moisture", 3 / 7),
        ("msi", 0.4),
        ("reci", 1.5),
        ("nbr", 0.25),
        ("ccci", (3 / 7) / (0.35 / 0.65)),
        ("bsi", -0.1),
    ],
)
@pytest.mark.parametrize("quality", [True, False])
def test_block_means_precede_ratio_and_any_bad_sample_excludes_cell(
    monkeypatch, index, expected, quality, tmp_path
):
    seen = {}

    def post(url, *, json, **kwargs):
        seen.update(json)
        return httpx.Response(
            200, content=provider(json, index, quality), request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(cdse_client, "_throttle_process_api", lambda: None)
    monkeypatch.setattr(cdse_client.CdseClient, "token", lambda self: "fixture")
    args = dict(
        index=index,
        bbox=BBOX,
        time_from="2026-10-01T00:00:00Z",
        time_to="2026-10-01T23:59:59Z",
        with_native_qa=quality,
    )
    out = cdse_client.CdseClient().process_index(**args)
    image = out.tiff if quality else out
    path = tmp_path / "output.tif"
    path.write_bytes(image)
    with rasterio.open(path) as src:
        assert (src.width, src.height) == (2, 2)
        assert tuple(src.bounds) == pytest.approx(BBOX)
        values = src.read(1)
        assert values[0, 1] == pytest.approx(expected)
        assert np.isfinite(values).sum() == 1
        if quality:
            measured, receipt = native.measured_pixels(src, out, str(path))
            assert np.isfinite(measured).sum() == 1
            assert receipt["native_cloud_pixels"] == 1
            assert receipt["native_invalid_scl_pixels"] == 1
            assert receipt["scene_id"] == "cdse:sh:42"
            assert receipt["request_sha256"] == native.request_digest(seen)
            assert out.source_tiff_sha256 != out.tiff_sha256
            scene = {"bbox": BBOX, "datetime": "2026-10-01T12:00:00Z"}
            assert (
                cdse_client.backfill_request_identity(scene, index, None)[0] == out.request_sha256
            )


def test_small_field_never_expanded_and_coarse_band_resolution_is_explicit():
    for index in ("ndre", "ndmi", "ndvi", "ndsi", "truecolor"):
        dims, factors = cdse_client._sampling_grid(index, [44, 15, 44.00006, 15.00006])
        assert dims == factors == (1, 1)
    assert cdse_client._sampling_grid("ndsi", BBOX)[0] == (2, 2)
    assert cdse_client._sampling_grid("ndvi", BBOX)[0] == (4, 4)
    assert cdse_client.spatial_sampling("ndre")["native_band_resolution_m"] == {
        "B05": 20,
        "B08": 10,
    }


@pytest.mark.parametrize(
    "fault,reason",
    [
        ({"invalid_mask": True}, "cdse_reflectance_qa_invalid"),
        ({"mixed": True}, "cdse_reflectance_mixed_contributor_block"),
    ],
)
def test_bad_qa_and_mixed_scene_are_refused(fault, reason):
    import cdse_reflectance

    index = "ndmi"
    payload = cdse_client.build_process_payload(
        index=index, bbox=BBOX, time_from="2026-10-01T00:00:00Z", time_to="2026-10-01T23:59:59Z"
    )
    tiff = provider(payload, index, False, **fault)
    with pytest.raises(ValueError, match=reason):
        cdse_reflectance.finish(
            tiff, index, cdse_client.INDEX_EXPR[index][0], payload, (2, 2), False
        )


@pytest.mark.parametrize("index", ["msi", "reci", "nbr", "ccci", "bsi"])
def test_mixed_grid_respects_wire_size_and_narrow_fields(index):
    from cdse_native_product import MAX_RESPONSE_BYTES

    wire_bands = len(cdse_client.INDEX_EXPR[index][0]) + 3
    (w, h), factors = cdse_client._sampling_grid(index, [43, 14, 45, 16])
    assert w * h * wire_bands * 4 + 1024**2 <= MAX_RESPONSE_BYTES
    assert max(w, h) <= 2500 and factors == (2, 2)
    dims, factors = cdse_client._sampling_grid(index, [44, 15, 44.00006, 15.0004])
    assert dims == (1, 4) and factors == (1, 2)
    assert "block_mean_reflectance" in cdse_client.spatial_sampling(index)["resampling_method"]


@pytest.mark.parametrize("invalid", ["negative", "nodata"])
def test_one_bad_input_in_last_band_excludes_entire_cell(invalid):
    import cdse_reflectance

    index = "bsi"
    bands = cdse_client.INDEX_EXPR[index][0]
    payload = cdse_client.build_process_payload(
        index=index, bbox=BBOX, time_from="2026-10-01T00:00:00Z", time_to="2026-10-01T23:59:59Z"
    )
    with rasterio.MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=4,
            height=4,
            count=7,
            dtype="float32",
            nodata=9.0,
            crs="EPSG:4326",
            transform=from_bounds(*BBOX, 4, 4),
        ) as src:
            data = np.ones((7, 4, 4), dtype="float32")
            data[-3] = 4
            data[len(bands) - 1, 0, 1] = -0.01 if invalid == "negative" else 9.0
            src.write(data)
        result = cdse_reflectance.finish(mem.read(), index, bands, payload, (2, 2), False)
    with rasterio.MemoryFile(result) as out, out.open() as src:
        values = src.read(1)
    assert np.isnan(values[0, 0])
    assert np.count_nonzero(values == 0) == 3
