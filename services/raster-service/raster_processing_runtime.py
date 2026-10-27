"""Runtime context adapters for raster processing jobs.

This module lets routers schedule processing jobs without importing ``main``.
It assembles the small context object still required by the staged
``raster_job_orchestration`` helpers from the extracted modules.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit

import band_math
import object_store
import raster_api_models as api_models
import raster_asset_persistence
import raster_job_orchestration
import raster_pixel_processing
import raster_quality
import raster_runtime_state
import raster_security_context
import raster_settings
import raster_stage_receipt
import raw_data_processing
import trial_zonal_outcomes
from fastapi import HTTPException

logger = logging.getLogger("raster-service")


def make_processing_context(*, upload_dir: str | None = None) -> SimpleNamespace:
    """Build the minimal ctx object needed by processing/backfill/CDSE helpers.

    ``upload_dir`` is injectable so legacy tests that patch ``main.UPLOAD_DIR``
    can keep exercising the same filesystem path without requiring helpers to
    depend on ``main`` as their context object.
    """
    ctx = SimpleNamespace()
    ctx._jobs = raster_runtime_state.JOBS
    ctx._layers = raster_runtime_state.LAYERS
    # فهرس حقل→[طبقات] (raster_job_orchestration.run_processing يقيّده على كلّ معالجة لحقل).
    # كان غيابه يرمي AttributeError على كلّ تشغيلة backfill لحقل (SimpleNamespace بلا
    # _field_layers) فتفشل المعالجة صامتاً. نفس singleton المشترَك الذي يقرأه القرّاء.
    ctx._field_layers = raster_runtime_state.FIELD_LAYERS
    ctx.JobStatus = api_models.JobStatus
    ctx.ProcessRequest = api_models.ProcessRequest
    ctx.IndicatorKind = api_models.IndicatorKind
    ctx.SourceFormat = api_models.SourceFormat
    ctx.BandMapping = api_models.BandMapping
    ctx.HTTPException = HTTPException
    ctx.RASTER_NODATA = raster_settings.RASTER_NODATA
    ctx.UPLOAD_DIR = upload_dir or raster_settings.UPLOAD_DIR
    ctx._INDICATOR_FORMULAS = raster_quality.INDICATOR_FORMULAS
    ctx._quality_from_cloud_pct = raster_quality.quality_from_cloud_pct
    ctx._safe_raster_source = lambda url: raster_security_context.safe_raster_source(
        url, ctx.UPLOAD_DIR, raster_settings.SSRF_BLOCKED_HOSTS
    )
    ctx.object_store = object_store
    ctx.band_math = band_math
    ctx.logger = logger
    ctx._persist_raster_asset = raster_asset_persistence.persist_raster_asset
    ctx._process_precomputed_pixels = lambda req, layer_id: (
        raster_pixel_processing.process_precomputed_pixels(ctx, req, layer_id)
    )
    ctx._process_pixels = lambda req, layer_id: raster_pixel_processing.process_pixels(
        ctx, req, layer_id
    )
    ctx._run_processing = lambda job_id, req: raster_job_orchestration.run_processing(
        ctx, job_id, req
    )
    return ctx


def _artifact_ref(url) -> str:
    """Identity of a source/output for a stage receipt, without credentials.

    Receipts are logged; a presigned URL carries its signature in the query string
    and userinfo may carry a password, so only scheme/host/path are kept.
    """
    if not url:
        return ""
    parts = urlsplit(str(url))
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def run_processing(
    job_id: str, req: api_models.ProcessRequest, *, upload_dir: str | None = None
) -> None:
    """Run a single raster processing job and emit a structured stage receipt.

    The orchestration records failures as job state instead of raising, so a
    normal return is not success: the receipt follows the persisted job outcome.
    Only ``completed`` (durably persisted) closes it as completed; ``failed`` and
    ``processed_unpublished`` close it as failed with the job's stable code.
    """
    req_payload = req.model_dump(mode="json") if hasattr(req, "model_dump") else vars(req)
    receipt = raster_stage_receipt.begin_stage(
        stage_id="raster.process",
        stage_version="v1",
        run_id=str(job_id),
        config=req_payload,
        input_refs=[_artifact_ref(req_payload.get("raster_url"))],
    )
    ctx = make_processing_context(upload_dir=upload_dir)
    try:
        raster_job_orchestration.run_processing(ctx, job_id, req)
    except Exception as exc:
        logger.info(
            "raster_stage_receipt=%s",
            json.dumps(raster_stage_receipt.fail_stage(receipt, exc), sort_keys=True),
        )
        raise
    job = ctx._jobs.get(job_id) or {}
    status = job.get("status")
    status = str(getattr(status, "value", status) or "")
    if status == api_models.JobStatus.completed.value:
        layer_id = (job.get("result") or {}).get("layer_id")
        cog_url = (ctx._layers.get(layer_id) or {}).get("cog_url") if layer_id else None
        closed = raster_stage_receipt.finish_stage(
            receipt,
            output_refs=[f"layer:{layer_id}" if layer_id else "", _artifact_ref(cog_url)],
        )
    else:
        closed = raster_stage_receipt.fail_stage(
            receipt,
            str(
                job.get("error_code")
                or job.get("error_message")
                or f"job_not_completed:{status or 'unknown'}"
            ),
        )
    logger.info("raster_stage_receipt=%s", json.dumps(closed, sort_keys=True))


def run_batch_processing(
    job_id: str, req: api_models.BatchProcessRequest, *, upload_dir: str | None = None
) -> None:
    """Run a batch raster processing job without depending on main.py."""
    raster_job_orchestration.run_batch_processing(
        make_processing_context(upload_dir=upload_dir), job_id, req
    )


def process_precomputed_pixels(
    req: api_models.ProcessRequest, layer_id: str, *, upload_dir: str | None = None
):
    """Process a precomputed single-band raster using an explicit context."""
    return raster_pixel_processing.process_precomputed_pixels(
        make_processing_context(upload_dir=upload_dir), req, layer_id
    )


def process_precomputed_truecolor(req: api_models.ProcessRequest, *, upload_dir: str | None = None):
    """Process a precomputed truecolor raster using an explicit context."""
    return raster_pixel_processing.process_precomputed_truecolor(
        make_processing_context(upload_dir=upload_dir), req
    )


def process_pixels(req: api_models.ProcessRequest, layer_id: str, *, upload_dir: str | None = None):
    """Process a source raster using an explicit context."""
    return raster_pixel_processing.process_pixels(
        make_processing_context(upload_dir=upload_dir), req, layer_id
    )


def process_raw_raster(req: api_models.RawDataProcessRequest, *, upload_dir: str | None = None):
    """Inspect raw raster data without computing agronomic indicators."""
    return raw_data_processing.process_raw_raster(
        make_processing_context(upload_dir=upload_dir), req
    )


def extract_trial_zonal_outcomes(
    assignments: list[dict], raster_layers: list[dict], *, all_touched: bool = False
):
    """Existing raster-service façade for exact plot-wise trial evidence extraction."""
    return trial_zonal_outcomes.extract_plot_zonal_outcomes(
        assignments, raster_layers, all_touched=all_touched
    )
