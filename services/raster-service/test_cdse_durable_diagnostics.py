"""Retain observed failure evidence without inventing CDSE's upstream cause."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import cdse_singleflight
import httpx
import numpy as np
import pytest
import raster_cdse_tile_runtime as runtime
import raster_settings
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

pytestmark = pytest.mark.unit
LOG = logging.getLogger(__name__)
SECRET = "Bearer do-not-retain-this-token"


def _tiff(values):
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=2,
            height=2,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(0, 2, 1, 1),
            nodata=float("nan"),
        ) as dst:
            dst.write(np.array(values, dtype="float32"), 1)
        return mem.read()


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(raster_settings, "UPLOAD_DIR", str(tmp_path))
    cdse_singleflight.cdse_tile_cache.clear()
    yield
    for _expires, name in cdse_singleflight.cdse_tile_cache.values():
        Path(name).unlink(missing_ok=True)
    cdse_singleflight.cdse_tile_cache.clear()


async def _run(monkeypatch, *, payload=b"", error=None, geometry=None, latest=False):
    class Client:
        def process_index(self, **kwargs):
            if error:
                raise error
            return payload

        def search_scenes(self, **kwargs):
            return []

    monkeypatch.setattr(runtime._cdse, "get_client", Client)
    return await runtime.ensure_field_cog(
        "field-one",
        "ndvi",
        "2026-10-14",
        "2026-10-01T00:00:00Z" if latest else "2026-10-14T00:00:00Z",
        "2026-10-14T23:59:59Z",
        [0, 0, 2, 2],
        geometry,
        bool(geometry),
        logger=LOG,
    )


def _receipt(tmp_path):
    paths = list((tmp_path / "cdse_diagnostics").glob("*.json"))
    assert len(paths) == 1, "failure evidence must outlive the discarded TIFF and process log"
    return json.loads(paths[0].read_text())


async def test_empty_tiff_retains_request_and_response_evidence_without_claiming_cause(
    monkeypatch, tmp_path
):
    payload = _tiff([[np.nan] * 2] * 2)
    assert await _run(monkeypatch, payload=payload) is None
    record = _receipt(tmp_path)
    assert record["request"]["bbox"] == [0, 0, 2, 2]
    assert record["request"]["max_cloud_pct"] == 40.0
    assert record["response"]["bytes"] == len(payload)
    assert record["response"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert record["response"]["after_mask"]["readable"] is True
    assert record["response"]["after_mask"]["observable_pixels"] == 0
    assert record["attribution"] == "unknown"
    assert record["historical_cause"] == "not_reconstructed"
    assert cdse_singleflight.cdse_tile_cache == {}


async def test_mask_attribution_requires_observed_pixels_before_and_none_after(
    monkeypatch, tmp_path
):
    outside = {"type": "Polygon", "coordinates": [[[3, 3], [4, 3], [4, 4], [3, 4], [3, 3]]]}
    assert await _run(monkeypatch, payload=_tiff([[0.2] * 2] * 2), geometry=outside) is None
    record = _receipt(tmp_path)
    assert record["response"]["before_mask"]["observable_pixels"] == 4
    assert record["response"]["after_mask"]["observable_pixels"] == 0
    assert record["attribution"] == "polygon_mask_removed_observations"


async def test_unreadable_payload_is_unknown_not_mask_or_no_assets(monkeypatch, tmp_path):
    assert await _run(monkeypatch, payload=b"not-a-tiff") is None
    record = _receipt(tmp_path)
    assert record["outcome"] == "content_check_failed"
    assert record["response"]["after_mask"]["readable"] is False
    assert record["response"]["after_mask"]["observable_pixels"] is None
    assert record["attribution"] == "unknown"


@pytest.mark.parametrize(
    "status,headers,attribution",
    [
        (401, {}, "authentication_rejected"),
        (403, {}, "forbidden_reason_unknown"),
        (403, {"WWW-Authenticate": 'Bearer error="insufficient_scope"'}, "scope_rejected"),
        (429, {}, "rate_limited"),
        (503, {}, "provider_transient_failure"),
        (404, {}, "unknown"),
        (501, {}, "unknown"),
    ],
)
async def test_provider_status_is_evidence_not_a_guessed_empty_scene_cause(
    monkeypatch, tmp_path, status, headers, attribution
):
    request = httpx.Request(
        "POST",
        "https://cdse.invalid/process?access_token=" + SECRET,
        headers={"Authorization": SECRET},
    )
    response = httpx.Response(status, request=request, headers=headers, text=SECRET)
    error = httpx.HTTPStatusError(SECRET, request=request, response=response)
    assert await _run(monkeypatch, error=error) is None
    record = _receipt(tmp_path)
    assert record["attribution"] == attribution
    assert record["response"]["http_status"] == status
    assert SECRET not in json.dumps(record)
    assert "Authorization" not in json.dumps(record)


async def test_transport_failure_is_observed_but_does_not_reveal_exception_text(
    monkeypatch, tmp_path
):
    assert await _run(monkeypatch, error=httpx.ReadTimeout(SECRET)) is None
    record = _receipt(tmp_path)
    assert record["attribution"] == "transport_failure"
    assert SECRET not in json.dumps(record)


async def test_empty_catalog_list_is_unknown_because_legacy_client_hides_failures(
    monkeypatch, tmp_path
):
    assert await _run(monkeypatch, latest=True) is None
    record = _receipt(tmp_path)
    assert record["outcome"] == "no_selected_scene"
    assert record["attribution"] == "unknown"
    assert record["response"]["catalogue_evidence"] == "not_available"


async def test_real_observation_still_caches_without_creating_failure_receipt(
    monkeypatch, tmp_path
):
    assert await _run(monkeypatch, payload=_tiff([[0.2] * 2] * 2)) is not None
    assert not list((tmp_path / "cdse_diagnostics").glob("*.json"))


async def test_storage_failure_does_not_cache_empty_data_or_claim_a_retained_receipt(
    monkeypatch, tmp_path, caplog
):
    import cdse_diagnostics

    def fail(_):
        raise OSError(SECRET)

    monkeypatch.setattr(cdse_diagnostics, "persist", fail)
    with caplog.at_level(logging.INFO):
        assert await _run(monkeypatch, payload=_tiff([[np.nan] * 2] * 2)) is None
    assert "persistence unconfirmed: OSError" in caplog.text
    assert "receipt retained" not in caplog.text
    assert SECRET not in caplog.text
    assert cdse_singleflight.cdse_tile_cache == {}
    assert not list((tmp_path / "cdse_diagnostics").glob("*.json"))


async def test_receipt_survives_a_fresh_interpreter(monkeypatch, tmp_path):
    import subprocess
    import sys

    assert await _run(monkeypatch, payload=_tiff([[np.nan] * 2] * 2)) is None
    path = next((tmp_path / "cdse_diagnostics").glob("*.json"))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,sys; print(json.load(open(sys.argv[1]))['outcome'])",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "empty_raster"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def _new_receipt():
    import cdse_diagnostics

    return cdse_diagnostics.failure_receipt(
        tenant=SECRET,
        field_id="../../" + SECRET,
        index=SECRET,
        date_from=SECRET,
        date_to=SECRET,
        bbox=[0, 0, 2, 2],
        geometry={"secret": SECRET},
        max_cloud_pct=40,
        outcome="empty_raster",
        payload=SECRET.encode(),
        scene_id=SECRET,
        before_mask={"readable": True, "observable_pixels": 4, "Authorization": SECRET},
        after_mask={"readable": True, "observable_pixels": 0, "access_token": SECRET},
    )


def test_allowlist_hashes_identifiers_and_does_not_copy_arbitrary_provider_or_request_text():
    record = _new_receipt()
    assert SECRET not in json.dumps(record)
    assert "Authorization" not in json.dumps(record)
    assert "access_token" not in json.dumps(record)
    assert record["request"]["date_from"] is None


def test_concurrent_writers_bound_retention_and_recover_interrupted_files(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    import cdse_diagnostics

    monkeypatch.setattr(cdse_diagnostics, "MAX_RECEIPTS", 4)
    directory = tmp_path / "cdse_diagnostics"
    directory.mkdir(mode=0o700)
    stale = directory / ("a" * 32 + ".tmp")
    stale.write_bytes(b"interrupted")
    unrelated = directory / "operator-note.txt"
    unrelated.write_text("retain this file")
    with ThreadPoolExecutor(max_workers=8) as workers:
        ids = list(workers.map(lambda _: cdse_diagnostics.persist(_new_receipt()), range(16)))
    files = list(directory.glob("*.json"))
    assert len(files) == 4
    assert not stale.exists()
    assert unrelated.read_text() == "retain this file"
    assert not list(directory.glob("*.tmp"))
    assert {json.loads(p.read_text())["receipt_id"] for p in files} <= set(ids)
    assert all(p.stat().st_size <= cdse_diagnostics.MAX_RECEIPT_BYTES for p in files)


def test_oversized_receipt_is_rejected_without_growing_storage(monkeypatch, tmp_path):
    import cdse_diagnostics

    record = _new_receipt()
    monkeypatch.setattr(cdse_diagnostics, "MAX_RECEIPT_BYTES", 10)
    with pytest.raises(ValueError, match="diagnostic_receipt_too_large"):
        cdse_diagnostics.persist(record)
    assert not (tmp_path / "cdse_diagnostics").exists()


def test_failed_atomic_replace_leaves_no_partial_receipt(monkeypatch, tmp_path):
    import cdse_diagnostics

    def fail(*_args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(cdse_diagnostics.os, "replace", fail)
    with pytest.raises(OSError, match="disk unavailable"):
        cdse_diagnostics.persist(_new_receipt())
    assert not list((tmp_path / "cdse_diagnostics").glob("*.json"))
    assert not list((tmp_path / "cdse_diagnostics").glob("*.tmp"))


def test_cleanup_failure_releases_writer_lock(monkeypatch, tmp_path):
    import fcntl
    import os

    import cdse_diagnostics

    original_unlink = Path.unlink

    def fail_replace(*_args):
        raise OSError("replace failure")

    def fail_cleanup(path, *args, **kwargs):
        if path.suffix == ".tmp":
            raise PermissionError("cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(cdse_diagnostics.os, "replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(PermissionError, match="cleanup failure"):
        cdse_diagnostics.persist(_new_receipt())
    fd = os.open(tmp_path / "cdse_diagnostics/write.lock", os.O_RDWR)
    try:
        # Nonblocking acquisition fails if cleanup leaked the original lock.
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(fd)


@pytest.mark.parametrize("failure_stage", ["replace", "file_fsync", "directory_fsync"])
def test_failed_commit_preserves_all_previous_receipts(monkeypatch, tmp_path, failure_stage):
    import os
    import stat

    import cdse_diagnostics

    monkeypatch.setattr(cdse_diagnostics, "MAX_RECEIPTS", 2)
    for _ in range(2):
        cdse_diagnostics.persist(_new_receipt())
    directory = tmp_path / "cdse_diagnostics"
    before = {p.name: p.read_bytes() for p in directory.glob("*.json")}
    original_fsync = os.fsync
    replaced = False
    original_replace = os.replace

    def replace(*args):
        nonlocal replaced
        if failure_stage == "replace":
            raise OSError("commit failed")
        original_replace(*args)
        replaced = True

    def fsync(fd):
        is_directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        if (failure_stage == "file_fsync" and not is_directory) or (
            failure_stage == "directory_fsync" and is_directory and replaced
        ):
            raise OSError("commit failed")
        original_fsync(fd)

    monkeypatch.setattr(cdse_diagnostics.os, "replace", replace)
    monkeypatch.setattr(cdse_diagnostics.os, "fsync", fsync)
    with pytest.raises(OSError, match="commit failed"):
        cdse_diagnostics.persist(_new_receipt())
    after = {p.name: p.read_bytes() for p in directory.glob("*.json")}
    assert all(after.get(name) == content for name, content in before.items())
    assert len(after) <= 3  # a committed but unconfirmed replacement may remain


def test_rotation_failure_stops_growth_then_recovers(monkeypatch, tmp_path):
    import cdse_diagnostics

    monkeypatch.setattr(cdse_diagnostics, "MAX_RECEIPTS", 2)
    for _ in range(2):
        cdse_diagnostics.persist(_new_receipt())
    directory = tmp_path / "cdse_diagnostics"
    original_unlink = Path.unlink

    def fail_rotation(path, *args, **kwargs):
        if path.suffix == ".json":
            raise PermissionError("rotation failed")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(Path, "unlink", fail_rotation)
        for _ in range(3):
            with pytest.raises(PermissionError, match="rotation failed"):
                cdse_diagnostics.persist(_new_receipt())
            assert len(list(directory.glob("*.json"))) == 3
    latest = cdse_diagnostics.persist(_new_receipt())
    assert len(list(directory.glob("*.json"))) == 2
    assert (directory / (latest + ".json")).exists()


async def test_content_inspection_failure_is_not_recorded_as_empty(monkeypatch, tmp_path):
    import tile_render

    def fail(*_args):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(tile_render, "raster_has_observable_content", fail)
    assert await _run(monkeypatch, payload=_tiff([[0.2] * 2] * 2)) is None
    receipt = _receipt(tmp_path)
    assert receipt["outcome"] == "content_check_failed"
    assert receipt["response"]["after_mask"] is None
    assert SECRET not in json.dumps(receipt)
    assert cdse_singleflight.cdse_tile_cache == {}


async def test_small_valid_raster_has_measured_count_but_remains_cache_ineligible(
    monkeypatch, tmp_path
):
    import tile_render

    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=1,
            height=1,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(0, 2, 1, 1),
            nodata=float("nan"),
        ) as dst:
            dst.write(np.array([[0.2]], dtype="float32"), 1)
        payload = mem.read()
    path = tmp_path / "one.tif"
    path.write_bytes(payload)
    assert tile_render.raster_content_observation(str(path))["observable_pixels"] == 1
    assert tile_render.raster_has_observable_content(str(path)) is False
    assert await _run(monkeypatch, payload=payload) is None
    receipt = _receipt(tmp_path)
    assert receipt["outcome"] == "content_rejected"
    assert receipt["response"]["after_mask"]["observable_pixels"] == 1
    assert cdse_singleflight.cdse_tile_cache == {}
