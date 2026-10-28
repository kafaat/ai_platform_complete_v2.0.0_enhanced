"""Native TIFF/TAR fixtures, not live provider or production acceptance."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from types import SimpleNamespace

import cdse_client
import cdse_native_product as native
import httpx
import numpy as np
import pytest
import rasterio
from raster_api_models import ProcessRequest
from rasterio.transform import from_origin

pytestmark = pytest.mark.unit


def product_bytes(*, cloudy=False, mixed=False, invalid_mask=False):
    array = np.ones((4, 10, 10), dtype="float32")
    array[0] = 0.6
    array[1] = 4
    if cloudy:
        array[1, 0, :] = 9
        array[2, 1, :] = 0
    if mixed:
        array[3, 0, :] = 2
    if invalid_mask:
        array[2, 0, 0] = 2
    with rasterio.MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=10,
            width=10,
            count=4,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(44, 15, 0.01, 0.01),
        ) as dst:
            dst.write(array)
        return mem.read()


def archive_bytes(tiff, *, tiles=None, extra=None):
    metadata = {
        "schema": native.SCHEMA,
        "tiles": tiles
        or [
            {"id": "123", "date": "2026-10-01T07:30:00Z"},
            {"id": "456", "date": "2026-10-02T07:30:00Z"},
        ],
    }
    mem = io.BytesIO()
    with tarfile.open(fileobj=mem, mode="w") as archive:
        parts = {"default.tif": tiff, "userdata.json": json.dumps(metadata).encode()}
        if extra:
            parts.update(extra)
        for name, content in parts.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return mem.getvalue()


def request(tmp_path, *, cloudy=False):
    tiff = product_bytes(cloudy=cloudy)
    product = native.decode_response(
        archive_bytes(tiff), native.build_evalscript("ndvi", cdse_client.INDEX_EXPR)
    )
    path = tmp_path / "product.tif"
    path.write_bytes(tiff)
    req = ProcessRequest(
        tenant_id="",
        field_id="f",
        raster_url=str(path),
        indicator="ndvi",
        source_format="sentinel2_l2a",
        bands={},
        provider="cdse",
        precomputed_index=True,
        scene_id="catalogue-candidate",
        capture_datetime="2026-10-03T12:00:00Z",
    )
    req._cdse_native_product = product
    return req, product


def test_client_requests_native_qa_and_decodes_request_bound_receipt(monkeypatch):
    tiff = product_bytes()
    captured = {}

    def post(url, *, json, headers, timeout):
        captured.update(payload=json, headers=headers)
        return httpx.Response(200, content=archive_bytes(tiff), request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(cdse_client, "_throttle_process_api", lambda: None)
    monkeypatch.setattr(cdse_client.CdseClient, "token", lambda self: "test-token")
    result = cdse_client.CdseClient().process_index(
        index="ndvi",
        bbox=[44, 15, 44.01, 15.01],
        time_from="2026-10-01T00:00:00Z",
        time_to="2026-10-01T23:59:59Z",
        with_native_qa=True,
    )
    assert isinstance(result, native.NativeProduct)
    assert result.tiff_sha256 == hashlib.sha256(tiff).hexdigest()
    assert (
        result.evalscript_sha256
        == hashlib.sha256(captured["payload"]["evalscript"].encode()).hexdigest()
    )
    assert captured["headers"]["Accept"] == "application/tar"
    assert captured["payload"]["output"]["responses"][1]["identifier"] == "userdata"


def test_native_masks_and_measured_contributor_replace_request_guesses(tmp_path):
    req, product = request(tmp_path, cloudy=True)
    with rasterio.open(req.raster_url) as src:
        array, observed = native.measured_pixels(src, product, req.raster_url)
    assert np.isfinite(array).sum() == 80
    assert observed["native_cloud_pixels"] == 10
    assert observed["scene_id"] == "cdse:sh:123"
    assert observed["acquisition_datetime"] == "2026-10-01T07:30:00+00:00"


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"mixed": True}, "single_contributor"),
        ({"invalid_mask": True}, "data_mask_invalid"),
    ],
)
def test_native_qa_rejects_unproven_or_invalid_contributors(tmp_path, change, reason):
    tiff = product_bytes(**change)
    product = native.decode_response(archive_bytes(tiff), "script")
    path = tmp_path / "product.tif"
    path.write_bytes(tiff)
    with rasterio.open(path) as src, pytest.raises(ValueError, match=reason):
        native.measured_pixels(src, product, str(path))


def test_changed_tiff_cannot_reuse_native_receipt(tmp_path):
    req, product = request(tmp_path)
    with open(req.raster_url, "ab") as stream:
        stream.write(b"changed")
    with rasterio.open(req.raster_url) as src, pytest.raises(ValueError, match="checksum_mismatch"):
        native.measured_pixels(src, product, req.raster_url)


def test_provider_receipt_cannot_be_injected_via_request_json(tmp_path):
    req, product = request(tmp_path)
    request_json = req.model_dump() | {"_cdse_native_product": product}
    assert ProcessRequest.model_validate(request_json)._cdse_native_product is None


def test_provider_tar_does_not_extract_arbitrary_members():
    with pytest.raises(ValueError, match="members_invalid"):
        native.decode_response(
            archive_bytes(product_bytes(), extra={"../../escape": b"secret"}), "script"
        )


@pytest.mark.parametrize(
    "tiles",
    [[{"id": "undefined", "date": "2026-10-01T00:00:00Z"}], [{"id": "123", "date": "2026-10-01"}]],
)
def test_missing_provider_identity_is_not_filled_from_catalogue(tiles):
    with pytest.raises(ValueError):
        native.decode_response(archive_bytes(product_bytes(), tiles=tiles), "script")


def test_actual_pixel_processor_emits_observed_mask_quality_and_time(tmp_path):
    from raster_processing_runtime import process_precomputed_pixels

    req, _ = request(tmp_path)
    stats, _, _, _ = process_precomputed_pixels(req, "layer", upload_dir=str(tmp_path))
    product = stats["validated_raster_product"]
    assert product["cloud_mask_applied"] is True
    assert product["provenance"]["qa_mask_version"] == native.MASK_VERSION
    assert req.scene_id == "cdse:sh:123"
    assert req.capture_datetime == "2026-10-01T07:30:00+00:00"
    assert stats["quality_score"] == product["quality_score"]
    assert stats["quality_score_semantics"] == "sahool.raster_pixel_qa/1"
    assert stats["quality_flags"]["qa_layer_present"] is True


def test_native_quality_and_algorithm_survive_actual_persistence_adapter(tmp_path, monkeypatch):
    import db_persist
    from raster_asset_persistence import persist_raster_asset
    from raster_processing_runtime import process_precomputed_pixels

    req, _ = request(tmp_path)
    stats, bounds, _, meta = process_precomputed_pixels(req, "layer", upload_dir=str(tmp_path))
    captured = {}

    async def insert(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(db_persist, "insert_raster_asset", insert)
    stats["confidence"] = 0.1  # Distinct semantic: must not replace native pixel QA.
    assert persist_raster_asset(req, "file:///product.tif", meta, bounds, stats)
    assert captured["quality_score"] == stats["quality_score"]
    assert captured["qa_mask_version"] == native.MASK_VERSION
    assert (
        captured["algorithm_version"]
        == stats["validated_raster_product"]["provenance"]["algorithm_version"]
    )
    assert captured["provenance"]["current_cog_uri"] == "file:///product.tif"
    measured = captured["provenance"]["stats"]
    assert measured["quality_score_semantics"] == "sahool.raster_pixel_qa/1"
    assert measured["cdse_native_qa"]["native_valid_pixels"] == 100


@pytest.mark.parametrize("scl", [0, 1])
def test_native_nodata_and_saturated_scl_never_count_as_valid(tmp_path, scl):
    raw = product_bytes()
    with rasterio.MemoryFile(raw) as mem:
        with mem.open() as src:
            data, profile = src.read(), src.profile
    data[1, 0, :] = scl
    with rasterio.MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(data)
        tiff = mem.read()
    product = native.decode_response(archive_bytes(tiff), "script")
    path = tmp_path / "scl.tif"
    path.write_bytes(tiff)
    with rasterio.open(path) as src:
        pixels, receipt = native.measured_pixels(src, product, str(path))
    assert np.isfinite(pixels).sum() == 90
    assert receipt["native_invalid_scl_pixels"] == 10


@pytest.mark.parametrize("dimensions", [(2501, 10), (10, 2501), (9, 10)])
def test_native_dimensions_rejected_before_pixel_allocation(tmp_path, dimensions):
    from dataclasses import replace

    req, product = request(tmp_path)
    product = replace(product, expected_width=10, expected_height=10)

    class HeaderOnly:
        crs = "EPSG:4326"
        count = 4
        width, height = dimensions

        def read(self):
            pytest.fail("invalid dimensions must be rejected before reading pixels")

    with pytest.raises(ValueError, match="dimensions"):
        native.measured_pixels(HeaderOnly(), product, req.raster_url)


def test_native_receipt_binds_exact_process_payload(monkeypatch):
    captured = {}

    def post(url, *, json, headers, timeout):
        captured.update(json)
        return httpx.Response(
            200, content=archive_bytes(product_bytes()), request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(cdse_client, "_throttle_process_api", lambda: None)
    monkeypatch.setattr(cdse_client.CdseClient, "token", lambda self: "test-token")
    scene = {"datetime": "2026-10-01T07:30:00Z", "bbox": [44, 15, 44.01, 15.01]}
    expected_sha, expected_algorithm = cdse_client.backfill_request_identity(scene, "ndvi", None)
    actual = cdse_client.CdseClient().process_index(
        index="ndvi",
        bbox=scene["bbox"],
        time_from="2026-10-01T00:00:00Z",
        time_to="2026-10-01T23:59:59Z",
        geometry=None,
        max_cloud_pct=40.0,
        with_native_qa=True,
    )
    assert actual.request_sha256 == expected_sha == native.request_digest(captured)
    assert expected_algorithm == "cdse-evalscript-sha256:" + actual.evalscript_sha256
    assert (actual.expected_width, actual.expected_height) == (
        captured["output"]["width"],
        captured["output"]["height"],
    )
    changed = dict(scene, datetime="2026-10-02T07:30:00Z")
    assert cdse_client.backfill_request_identity(changed, "ndvi", None)[0] != expected_sha


def _native_grid_tiff(*, crs, transform, size=16):
    array = np.ones((4, size, size), dtype="float32")
    array[0] = 0.5
    array[1] = 4
    with rasterio.MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=size,
            width=size,
            count=4,
            dtype="float32",
            crs=crs,
            transform=transform,
        ) as dst:
            dst.write(array)
        return mem.read()


def _native_grid_payload(bbox):
    return cdse_client.build_process_payload(
        index="ndvi",
        bbox=bbox,
        time_from="2026-10-01T00:00:00Z",
        time_to="2026-10-01T23:59:59Z",
        with_native_qa=True,
    )


def _measure_against_request(tmp_path, tiff, payload):
    product = native.decode_response(archive_bytes(tiff), "script", request_payload=payload)
    path = tmp_path / "grid.tif"
    path.write_bytes(tiff)
    with rasterio.open(path) as src:
        return native.measured_pixels(src, product, str(path))


@pytest.mark.parametrize(
    "crs,transform",
    [
        # P2-CDSE-2 witness: requested dimensions, EPSG:3857 near origin, not the bbox.
        ("EPSG:3857", from_origin(100, 100, 10, 10)),
        # Requested CRS and pixel size, displaced by one degree: another place.
        ("EPSG:4326", from_origin(45, 16.001, 0.001 / 16, 0.001 / 16)),
        # Requested CRS and origin, doubled pixel size: footprint does not close.
        ("EPSG:4326", from_origin(44, 15.001, 0.002 / 16, 0.002 / 16)),
    ],
)
def test_native_decoded_grid_must_match_requested_grid(tmp_path, crs, transform):
    payload = _native_grid_payload([44, 15, 44.001, 15.001])
    assert (payload["output"]["width"], payload["output"]["height"]) == (16, 16)
    tiff = _native_grid_tiff(crs=crs, transform=transform)
    with pytest.raises(ValueError, match="cdse_native_grid_does_not_match_request"):
        _measure_against_request(tmp_path, tiff, payload)


def test_native_decoded_grid_on_requested_bbox_is_accepted(tmp_path):
    from rasterio.transform import from_bounds

    bbox = [44, 15, 44.001, 15.001]
    payload = _native_grid_payload(bbox)
    assert (payload["output"]["width"], payload["output"]["height"]) == (16, 16)
    tiff = _native_grid_tiff(crs="EPSG:4326", transform=from_bounds(*bbox, 16, 16))
    pixels, receipt = _measure_against_request(tmp_path, tiff, payload)
    assert np.isfinite(pixels).sum() == 256
    assert receipt["native_valid_pixels"] == 256


def _truecolor_request(tmp_path, *, min_score, raw_qa_required=True):
    arr = np.full((4, 16, 16), 20, dtype="uint8")
    arr[3] = 255
    arr[:3, :8, :8] = 0  # opaque valid black
    arr[:3, :8, 8:] = 1  # opaque valid dim
    arr[3, 8:, 8:] = 0  # transparent: invalid
    path = tmp_path / "rgba.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=16,
        height=16,
        count=4,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(44, 15, 0.01, 0.01),
    ) as dst:
        dst.write(arr)
    return ProcessRequest(
        tenant_id="t",
        field_id="f",
        raster_url=str(path),
        indicator="truecolor",
        source_format="sentinel2_l2a",
        bands={},
        provider="cdse",
        precomputed_index=True,
        raw_qa_required=raw_qa_required,
        min_raw_quality_score=min_score,
    )


def test_precomputed_truecolor_enforces_requested_min_quality(tmp_path, monkeypatch):
    """P2-CDSE-1: TrueColor admits by the same requested QA threshold as scalar."""
    import object_store
    from fastapi import HTTPException
    from raster_processing_runtime import process_precomputed_truecolor

    uploads = []
    monkeypatch.setattr(object_store, "upload_cog", lambda p, k: uploads.append(k) or "file://x")
    req = _truecolor_request(tmp_path, min_score=1.0)
    with pytest.raises(HTTPException) as exc:
        process_precomputed_truecolor(req, upload_dir=str(tmp_path))
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "raw_raster_quality_below_threshold"
    assert exc.value.detail["quality_score"] < 1.0
    assert exc.value.detail["min_raw_quality_score"] == 1.0
    assert uploads == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rgba.tif"]


def test_precomputed_truecolor_threshold_respects_opt_out_and_passing_score(tmp_path):
    from raster_processing_runtime import process_precomputed_truecolor

    opted_out = _truecolor_request(tmp_path, min_score=1.0, raw_qa_required=False)
    stats, _, _, _ = process_precomputed_truecolor(opted_out, upload_dir=str(tmp_path))
    assert stats["valid_pixels"] == 192
    passing = _truecolor_request(tmp_path, min_score=stats["raw_quality_score"])
    stats, _, _, meta = process_precomputed_truecolor(passing, upload_dir=str(tmp_path))
    assert "validated_raster_product" in stats
    assert meta["raw_qa_required"] is True
