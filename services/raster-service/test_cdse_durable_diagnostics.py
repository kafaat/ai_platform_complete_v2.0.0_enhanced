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


def _new_receipt(**changes):
    import cdse_diagnostics

    values = dict(
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
    values.update(changes)
    return cdse_diagnostics.failure_receipt(**values)


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
        ids = list(
            workers.map(
                lambda n: cdse_diagnostics.persist(_new_receipt(field_id=f"field-{n}")), range(16)
            )
        )
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
    for n in range(2):
        cdse_diagnostics.persist(_new_receipt(field_id=f"old-{n}"))
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
        cdse_diagnostics.persist(_new_receipt(field_id="new"))
    after = {p.name: p.read_bytes() for p in directory.glob("*.json")}
    assert all(after.get(name) == content for name, content in before.items())
    assert len(after) <= 3  # a committed but unconfirmed replacement may remain


def test_rotation_failure_stops_growth_then_recovers(monkeypatch, tmp_path):
    import cdse_diagnostics

    monkeypatch.setattr(cdse_diagnostics, "MAX_RECEIPTS", 2)
    for n in range(2):
        cdse_diagnostics.persist(_new_receipt(field_id=f"old-{n}"))
    directory = tmp_path / "cdse_diagnostics"
    original_unlink = Path.unlink

    def fail_rotation(path, *args, **kwargs):
        if path.suffix == ".json":
            raise PermissionError("rotation failed")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(Path, "unlink", fail_rotation)
        for n in range(3):
            with pytest.raises(PermissionError, match="rotation failed"):
                cdse_diagnostics.persist(_new_receipt(field_id=f"new-{n}"))
            assert len(list(directory.glob("*.json"))) == 3
    latest = cdse_diagnostics.persist(_new_receipt(field_id="recovered"))
    assert len(list(directory.glob("*.json"))) == 2
    assert (directory / (latest + ".json")).exists()


def test_duplicate_burst_preserves_other_fields_and_avoids_file_fsync(monkeypatch, tmp_path):
    import os
    import stat
    from datetime import UTC, datetime

    import cdse_diagnostics as diagnostics

    monkeypatch.setattr(diagnostics, "_utc_now", lambda: datetime(2026, 10, 14, tzinfo=UTC))
    previous = {diagnostics.persist(_new_receipt(field_id=f"other-{n}")) for n in range(5)}
    repeated = diagnostics.persist(_new_receipt(field_id="repeated"))
    directory = tmp_path / "cdse_diagnostics"
    before = {p.name: p.read_bytes() for p in directory.glob("*.json")}
    sync_kinds = []
    original_fsync = os.fsync

    def fsync(fd):
        sync_kinds.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        original_fsync(fd)

    monkeypatch.setattr(diagnostics.os, "fsync", fsync)
    for _ in range(256):
        assert diagnostics.persist(_new_receipt(field_id="repeated")) == repeated
    after = {p.name: p.read_bytes() for p in directory.glob("*.json")}
    assert before == after, "Duplicates must not evict, refresh or rewrite any retained observation"
    assert set(p.removesuffix(".json") for p in after) == previous | {repeated}
    assert sync_kinds == [True] * 256, "Confirm existing directory durability without file rewrites"


def test_duplicate_window_expires_without_sliding_on_each_repeat(monkeypatch, tmp_path):
    from datetime import UTC, datetime, timedelta

    import cdse_diagnostics as diagnostics

    clock = [datetime(2026, 10, 14, tzinfo=UTC)]
    monkeypatch.setattr(diagnostics, "_utc_now", lambda: clock[0])
    original = diagnostics.persist(_new_receipt())
    clock[0] += timedelta(seconds=59)
    assert diagnostics.persist(_new_receipt()) == original
    clock[0] += timedelta(seconds=1)
    renewed = diagnostics.persist(_new_receipt())
    assert renewed != original
    paths = list((tmp_path / "cdse_diagnostics").glob("*.json"))
    assert len(paths) == 2
    clock[0] += timedelta(seconds=59)
    assert diagnostics.persist(_new_receipt()) == renewed


@pytest.mark.parametrize(
    "change",
    [
        {"tenant": "another-tenant"},
        {"field_id": "another-field"},
        {"index": "evi"},
        {"date_from": "2026-10-01"},
        {"date_to": "2026-10-14"},
        {"bbox": [1, 1, 3, 3]},
        {"geometry": {"different": "geometry"}},
        {"max_cloud_pct": 0},
        {"outcome": "content_check_failed"},
        {"stage": "process"},
        {"payload": b"different observed response"},
        {"scene_id": "different-scene"},
        {"before_mask": {"readable": True, "observable_pixels": 5}},
        {"after_mask": {"readable": False, "observable_pixels": None}},
        {"quota_exhausted": True, "before_mask": None},
    ],
)
def test_different_semantic_observations_are_not_suppressed(tmp_path, change):
    import cdse_diagnostics as diagnostics

    original = diagnostics.persist(_new_receipt())
    distinct = diagnostics.persist(_new_receipt(**change))
    assert distinct != original
    assert len(list((tmp_path / "cdse_diagnostics").glob("*.json"))) == 2


def test_same_status_with_changed_attribution_and_changed_status_remain_distinct(tmp_path):
    import cdse_diagnostics as diagnostics

    ids = []
    for status, headers in [
        (403, {}),
        (403, {"WWW-Authenticate": 'error="insufficient_scope"'}),
        (404, {}),
        (501, {}),
    ]:
        response = httpx.Response(
            status, headers=headers, request=httpx.Request("POST", "https://cdse.invalid")
        )
        error = httpx.HTTPStatusError("not retained", request=response.request, response=response)
        ids.append(diagnostics.persist(_new_receipt(error=error, before_mask=None)))
    assert len(set(ids)) == 4
    assert len(list((tmp_path / "cdse_diagnostics").glob("*.json"))) == 4


@pytest.mark.parametrize(
    "damage",
    [
        "json",
        "oversized",
        "schema",
        "extra",
        "missing_request",
        "id",
        "naive",
        "future",
        "expired",
        "duplicate_key",
        "retention",
        "deep",
        "nonfinite",
        "nonobject",
        "invalid_utf8",
    ],
)
def test_malformed_or_unusable_previous_receipt_cannot_suppress(monkeypatch, tmp_path, damage):
    from datetime import UTC, datetime, timedelta

    import cdse_diagnostics as diagnostics

    now = datetime(2026, 10, 14, tzinfo=UTC)
    monkeypatch.setattr(diagnostics, "_utc_now", lambda: now)
    old = _new_receipt()
    diagnostics.persist(old)
    path = tmp_path / "cdse_diagnostics" / (old["receipt_id"] + ".json")
    if damage == "json":
        data = b"not json"
    elif damage == "oversized":
        data = b" " * (diagnostics.MAX_RECEIPT_BYTES + 1)
    elif damage == "deep":
        data = b"[" * 1100 + b"]" * 1100
    elif damage == "nonobject":
        data = b"null"
    elif damage == "invalid_utf8":
        data = b"\xff"
    else:
        if damage == "schema":
            old["schema"] = "unsupported.v2"
        elif damage == "extra":
            old["untrusted"] = SECRET
        elif damage == "missing_request":
            del old["request"]["tenant_sha256"]
        elif damage == "id":
            old["receipt_id"] = "0" * 32
        elif damage == "naive":
            old["observed_at"] = now.replace(tzinfo=None).isoformat()
        elif damage == "future":
            old["observed_at"] = (now + timedelta(seconds=1)).isoformat()
        elif damage == "expired":
            old["observed_at"] = (now - timedelta(seconds=60)).isoformat()
        elif damage == "retention":
            old["retention"] = {}
        elif damage == "nonfinite":
            old["request"]["bbox"] = [float("nan")] * 4
        data = json.dumps(old).encode()
        if damage == "duplicate_key":
            data = b'{"provider":"cdse",' + data[1:]
    path.write_bytes(data)
    current = _new_receipt()
    assert diagnostics.persist(current) == current["receipt_id"]
    assert path.read_bytes() == data
    assert len(list(path.parent.glob("*.json"))) == 2


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_duplicate_scan_never_follows_symlinks_or_blocks_on_special_files(tmp_path, kind):
    import os

    import cdse_diagnostics as diagnostics

    old = _new_receipt()
    directory = tmp_path / "cdse_diagnostics"
    directory.mkdir()
    path = directory / (old["receipt_id"] + ".json")
    outside = tmp_path / "operator-private.json"
    outside.write_text(json.dumps(old))
    if kind == "symlink":
        path.symlink_to(outside)
    else:
        os.mkfifo(path)
    current = _new_receipt()
    assert diagnostics.persist(current) == current["receipt_id"]
    assert outside.read_text() == json.dumps(old)


def test_concurrent_processes_reuse_the_same_recent_receipt(tmp_path):
    import subprocess
    import sys

    import cdse_diagnostics as diagnostics

    code = (
        "import sys,json;sys.path.insert(0,sys.argv[1]);"
        "import raster_settings,cdse_diagnostics;"
        "raster_settings.UPLOAD_DIR=sys.argv[2];"
        "print(cdse_diagnostics.persist(json.loads(sys.argv[3])))"
    )
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                code,
                str(Path(diagnostics.__file__).parent),
                str(tmp_path),
                json.dumps(_new_receipt()),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(3)
    ]
    ids = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr
        ids.append(stdout.strip())
    assert len(set(ids)) == 1
    assert len(list((tmp_path / "cdse_diagnostics").glob("*.json"))) == 1


def test_duplicate_directory_fsync_failure_is_not_success_and_releases_lock(monkeypatch, tmp_path):
    import fcntl
    import os

    import cdse_diagnostics as diagnostics

    receipt_id = diagnostics.persist(_new_receipt())

    def fail(_fd):
        raise OSError("directory sync unavailable")

    monkeypatch.setattr(diagnostics.os, "fsync", fail)
    with pytest.raises(OSError, match="directory sync unavailable"):
        diagnostics.persist(_new_receipt())
    directory = tmp_path / "cdse_diagnostics"
    assert [p.stem for p in directory.glob("*.json")] == [receipt_id]
    fd = os.open(directory / "write.lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(fd)


def test_duplicate_confirms_a_previous_rename_whose_directory_sync_failed(monkeypatch, tmp_path):
    import os
    import stat

    import cdse_diagnostics as diagnostics

    original_sync = diagnostics._sync_directory
    calls = 0

    def fail_after_rename(root):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("unconfirmed rename")
        original_sync(root)

    old = _new_receipt()
    with monkeypatch.context() as fault:
        fault.setattr(diagnostics, "_sync_directory", fail_after_rename)
        with pytest.raises(OSError, match="unconfirmed rename"):
            diagnostics.persist(old)
    directory = tmp_path / "cdse_diagnostics"
    before = {p.name: p.read_bytes() for p in directory.glob("*.json")}
    assert len(before) == 1
    sync_kinds = []
    original_fsync = os.fsync

    def fsync(fd):
        sync_kinds.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        original_fsync(fd)

    monkeypatch.setattr(diagnostics.os, "fsync", fsync)
    assert diagnostics.persist(_new_receipt()) == old["receipt_id"]
    assert sync_kinds == [True]
    assert {p.name: p.read_bytes() for p in directory.glob("*.json")} == before


def test_duplicate_reconciles_interrupted_rotation_before_returning(monkeypatch, tmp_path):
    import cdse_diagnostics as diagnostics

    monkeypatch.setattr(diagnostics, "MAX_RECEIPTS", 2)
    for n in range(2):
        diagnostics.persist(_new_receipt(field_id=f"old-{n}"))
    original_unlink = Path.unlink

    def fail_rotation(path, *args, **kwargs):
        if path.suffix == ".json":
            raise OSError("interrupted rotation")
        return original_unlink(path, *args, **kwargs)

    recent = _new_receipt(field_id="recent")
    with monkeypatch.context() as fault:
        fault.setattr(Path, "unlink", fail_rotation)
        with pytest.raises(OSError, match="interrupted rotation"):
            diagnostics.persist(recent)
    directory = tmp_path / "cdse_diagnostics"
    assert len(list(directory.glob("*.json"))) == 3
    assert diagnostics.persist(_new_receipt(field_id="recent")) == recent["receipt_id"]
    assert len(list(directory.glob("*.json"))) == 2


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
