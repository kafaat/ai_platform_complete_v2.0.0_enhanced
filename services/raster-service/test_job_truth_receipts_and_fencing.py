"""Job-truth contracts: receipts follow the job outcome; stale batch owners never publish.

PROC-01   — a processing job that terminates ``failed`` (orchestration swallows the
            exception and persists ``failed``) must not emit a ``completed`` stage
            receipt; the receipt binds the real source (``raster_url``) and outputs.
P3-DUR-3  — an indicator in flight when the batch lease is lost must not register a
            memory layer nor reach the durable persistence boundary.
P3-DUR-4  — ``finish_sync`` returning False (or raising) must not leave the local
            batch job claiming ``completed`` while the durable row stays processing.

Real orchestration and real stage receipts; only pixel computation, asset
persistence and the PostgreSQL lease store are replaced by in-process doubles.
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pytest
import raster_api_models as models
import raster_asset_persistence
import raster_batch_job_store
import raster_batch_runtime_leases
import raster_job_orchestration
import raster_pixel_processing
import raster_processing_runtime
import raster_runtime_state
import raster_stage_receipt
import rasterio
from rasterio.transform import from_origin

_TENANT = "00000000-0000-0000-0000-000000000001"


def _write_source(path) -> str:
    profile = {
        "driver": "GTiff",
        "width": 8,
        "height": 8,
        "count": 4,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(44.0, 16.0, 0.001, 0.001),
        "nodata": -9999.0,
    }
    with rasterio.open(path, "w", **profile) as dst:
        for band in range(1, 5):
            dst.write(np.full((8, 8), band / 10.0, dtype="float32"), band)
    return str(path)


def _pixel_result(layer_id: str):
    stats = {
        "min": 0.1,
        "max": 0.5,
        "mean": 0.3,
        "std": 0.1,
        "valid_pixels": 64,
        "nodata_pixels": 0,
    }
    meta = {"cog_url": f"s3://bucket/{layer_id}.tif"}
    return stats, [44.0, 15.992, 44.008, 16.0], 10.0, meta


def _receipts(caplog) -> list[dict]:
    out = []
    for rec in caplog.records:
        msg = rec.getMessage()
        if msg.startswith("raster_stage_receipt="):
            out.append(json.loads(msg.split("=", 1)[1]))
    return out


@pytest.fixture
def _clean_runtime_state():
    layers_before = set(raster_runtime_state.LAYERS)
    yield
    for key in set(raster_runtime_state.LAYERS) - layers_before:
        raster_runtime_state.LAYERS.pop(key, None)
    raster_batch_runtime_leases.clear()


def _single_request(source: str) -> models.ProcessRequest:
    return models.ProcessRequest(
        tenant_id=_TENANT,
        field_id="fld_job_truth",
        raster_url=source,
        indicator=models.IndicatorKind.ndvi,
        source_format=models.SourceFormat.custom,
        bands=models.BandMapping(red=1, nir=4),
        apply_cloud_mask=False,
        raw_qa_required=False,
    )


# ── PROC-01 ────────────────────────────────────────────────────────────────────────


def test_failed_processing_emits_failed_receipt_not_completed(
    tmp_path, monkeypatch, caplog, _clean_runtime_state
):
    source = _write_source(tmp_path / "scene.tif")

    def boom(ctx, req, layer_id, **kwargs):
        raise ValueError("pixel failure")

    monkeypatch.setattr(raster_pixel_processing, "process_pixels", boom)
    job_id = "job_truth_failed"
    raster_runtime_state.JOBS.set(job_id, {"job_id": job_id, "status": models.JobStatus.pending})
    caplog.set_level(logging.INFO, logger="raster-service")

    raster_processing_runtime.run_processing(
        job_id, _single_request(source), upload_dir=str(tmp_path)
    )

    job = raster_runtime_state.JOBS.get(job_id)
    assert str(job["status"]) == "failed"
    receipts = _receipts(caplog)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["status"] == "failed", receipt
    assert receipt["error_class"] == "raster_processing_failed"
    assert receipt["output_refs"] == []
    assert raster_stage_receipt.verify_receipt(receipt)
    # المصدر الحقيقيّ هو raster_url — كان المفتاح «source/source_url» فيُسجَّل فارغاً.
    assert receipt["input_refs"] == [source]


def test_completed_processing_receipt_binds_source_and_outputs(
    tmp_path, monkeypatch, caplog, _clean_runtime_state
):
    source = _write_source(tmp_path / "scene.tif")
    monkeypatch.setattr(
        raster_pixel_processing,
        "process_pixels",
        lambda ctx, req, layer_id, **kw: _pixel_result(layer_id),
    )
    monkeypatch.setattr(raster_asset_persistence, "persist_raster_asset", lambda *a, **k: True)
    job_id = "job_truth_completed"
    raster_runtime_state.JOBS.set(job_id, {"job_id": job_id, "status": models.JobStatus.pending})
    caplog.set_level(logging.INFO, logger="raster-service")

    raster_processing_runtime.run_processing(
        job_id, _single_request(source), upload_dir=str(tmp_path)
    )

    job = raster_runtime_state.JOBS.get(job_id)
    assert str(job["status"]) == "completed"
    (receipt,) = _receipts(caplog)
    assert receipt["status"] == "completed"
    assert receipt["input_refs"] == [source]
    layer_id = job["result"]["layer_id"]
    assert receipt["output_refs"] == [f"layer:{layer_id}", f"s3://bucket/{layer_id}.tif"]
    assert raster_stage_receipt.verify_receipt(receipt)


def test_unpublished_processing_is_not_receipted_as_completed(
    tmp_path, monkeypatch, caplog, _clean_runtime_state
):
    source = _write_source(tmp_path / "scene.tif")
    monkeypatch.setenv("RASTER_PERSISTENCE_MODE", "best_effort")
    monkeypatch.setattr(
        raster_pixel_processing,
        "process_pixels",
        lambda ctx, req, layer_id, **kw: _pixel_result(layer_id),
    )
    monkeypatch.setattr(raster_asset_persistence, "persist_raster_asset", lambda *a, **k: False)
    job_id = "job_truth_unpublished"
    raster_runtime_state.JOBS.set(job_id, {"job_id": job_id, "status": models.JobStatus.pending})
    caplog.set_level(logging.INFO, logger="raster-service")

    raster_processing_runtime.run_processing(
        job_id, _single_request(source), upload_dir=str(tmp_path)
    )

    assert str(raster_runtime_state.JOBS.get(job_id)["status"]) == "processed_unpublished"
    (receipt,) = _receipts(caplog)
    assert receipt["status"] == "failed"
    assert receipt["error_class"] == "raster_asset_not_persisted"


# ── P3-DUR-3 / P3-DUR-4 ───────────────────────────────────────────────────────────


class _Lease:
    """In-process stand-in for the PostgreSQL lease row of one batch claim."""

    def __init__(self, finish_result=True):
        self.owned = True
        self.finish_result = finish_result
        self.finish_calls: list[dict] = []
        self.heartbeats = 0

    def heartbeat_sync(self, **kwargs):
        self.heartbeats += 1
        return self.owned

    def finish_sync(self, **kwargs):
        self.finish_calls.append(kwargs)
        if isinstance(self.finish_result, BaseException):
            raise self.finish_result
        return self.finish_result


def _batch_setup(tmp_path, monkeypatch, lease: _Lease, job_id: str):
    source = _write_source(tmp_path / "scene.tif")
    monkeypatch.setattr(raster_batch_job_store, "heartbeat_sync", lease.heartbeat_sync)
    monkeypatch.setattr(raster_batch_job_store, "finish_sync", lease.finish_sync)
    ctx = raster_processing_runtime.make_processing_context(upload_dir=str(tmp_path))
    ctx._layers = {}
    ctx._field_layers = {}
    persist_calls: list[dict] = []

    def persist(req, cog_url, meta, bounds, stats, *, job_id):
        persist_calls.append({"job_id": job_id, "lease_owned": lease.owned})
        return True

    ctx._persist_raster_asset = persist
    raster_batch_runtime_leases.set_token(job_id, "lease-token-1")
    ctx._jobs.set(
        job_id,
        {
            "job_id": job_id,
            "status": models.JobStatus.pending,
            "batch_claim_key": "rib_job_truth",
            "claim_backend": "postgres",
        },
    )
    req = models.BatchProcessRequest(
        tenant_id=_TENANT,
        field_id="fld_job_truth",
        raster_url=source,
        indicators=[models.IndicatorKind.ndvi, models.IndicatorKind.ndmi],
        source_format=models.SourceFormat.custom,
        bands=models.BandMapping(red=1, nir=4, swir1=3),
        apply_cloud_mask=False,
        raw_qa_required=False,
    )
    return ctx, req, persist_calls


def test_lease_lost_during_indicator_blocks_layer_and_persistence(
    tmp_path, monkeypatch, _clean_runtime_state
):
    """Heartbeat thread already observed the loss while the indicator was computing."""
    lease = _Lease()
    job_id = "batch_job_truth_lost_flag"
    ctx, req, persist_calls = _batch_setup(tmp_path, monkeypatch, lease, job_id)
    beats: list = []
    real_cls = raster_job_orchestration._LeaseHeartbeat

    class _Captured(real_cls):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            beats.append(self)

    monkeypatch.setattr(raster_job_orchestration, "_LeaseHeartbeat", _Captured)

    def compute_then_lose(ctx_, single_req, layer_id, **kwargs):
        lease.owned = False  # takeover rotated the token during computation
        beats[0].lost_event.set()  # the periodic heartbeat noticed it
        return _pixel_result(layer_id)

    monkeypatch.setattr(raster_pixel_processing, "process_pixels", compute_then_lose)

    raster_job_orchestration.run_batch_processing(ctx, job_id, req)

    job = ctx._jobs.get(job_id)
    assert str(job["status"]) == "failed"
    assert job["error_message"] == "durable_lease_lost"
    assert ctx._layers == {}, "stale owner published an in-memory layer"
    assert ctx._field_layers == {}
    assert persist_calls == [], "stale owner reached the durable persistence boundary"
    child = ctx._jobs.get(f"{job_id}_ndvi")
    assert str(child["status"]) == "failed"
    assert child["error_message"] == "durable_lease_lost"
    assert lease.finish_calls == []


def test_ownership_is_reconfirmed_before_publication(tmp_path, monkeypatch, _clean_runtime_state):
    """Takeover happened mid-indicator but the periodic heartbeat has not run yet."""
    lease = _Lease()
    job_id = "batch_job_truth_takeover"
    ctx, req, persist_calls = _batch_setup(tmp_path, monkeypatch, lease, job_id)

    def compute_then_takeover(ctx_, single_req, layer_id, **kwargs):
        lease.owned = False
        return _pixel_result(layer_id)

    monkeypatch.setattr(raster_pixel_processing, "process_pixels", compute_then_takeover)

    raster_job_orchestration.run_batch_processing(ctx, job_id, req)

    job = ctx._jobs.get(job_id)
    assert str(job["status"]) == "failed"
    assert job["error_message"] == "durable_lease_lost"
    assert ctx._layers == {}
    assert persist_calls == []
    assert lease.finish_calls == []


def test_owned_lease_still_publishes_every_indicator(tmp_path, monkeypatch, _clean_runtime_state):
    lease = _Lease()
    job_id = "batch_job_truth_owned"
    ctx, req, persist_calls = _batch_setup(tmp_path, monkeypatch, lease, job_id)
    monkeypatch.setattr(
        raster_pixel_processing,
        "process_pixels",
        lambda ctx_, single_req, layer_id, **kw: _pixel_result(layer_id),
    )

    raster_job_orchestration.run_batch_processing(ctx, job_id, req)

    job = ctx._jobs.get(job_id)
    assert str(job["status"]) == "completed"
    assert len(ctx._layers) == 2
    assert [c["lease_owned"] for c in persist_calls] == [True, True]
    assert len(lease.finish_calls) == 1
    assert lease.finish_calls[0]["status"] == "completed"
    # التثبيت الحاضر لا يُترك على الـctx بعد انتهاء الدفعة.
    assert getattr(ctx, "_publication_fence", None) is None


@pytest.mark.parametrize("finish_result", [False, RuntimeError("db down")], ids=["false", "raises"])
def test_unacknowledged_durable_finish_does_not_leave_local_success(
    tmp_path, monkeypatch, finish_result, _clean_runtime_state
):
    lease = _Lease(finish_result=finish_result)
    job_id = "batch_job_truth_finish"
    ctx, req, _ = _batch_setup(tmp_path, monkeypatch, lease, job_id)
    monkeypatch.setattr(
        raster_pixel_processing,
        "process_pixels",
        lambda ctx_, single_req, layer_id, **kw: _pixel_result(layer_id),
    )

    raster_job_orchestration.run_batch_processing(ctx, job_id, req)

    assert len(lease.finish_calls) == 1
    job = ctx._jobs.get(job_id)
    assert str(job["status"]) != "completed", job
    assert str(job["status"]) == "failed"
    assert job["error_code"] == "durable_terminal_write_failed"
    assert job["publication_eligible"] is False
    assert raster_batch_runtime_leases.get_token(job_id) is None
