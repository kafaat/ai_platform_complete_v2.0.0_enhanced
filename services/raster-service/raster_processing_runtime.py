"""Runtime context adapters for raster processing jobs.

This module lets routers schedule processing jobs without importing ``main``.
It assembles the small context object still required by the staged
``raster_job_orchestration`` helpers from the extracted modules.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

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
from fastapi import HTTPException

logger = logging.getLogger("raster-service")


def make_processing_context() -> SimpleNamespace:
    """Build the minimal ctx object needed by ``raster_job_orchestration``."""
    ctx = SimpleNamespace()
    ctx._jobs = raster_runtime_state.JOBS
    ctx._layers = raster_runtime_state.LAYERS
    ctx.JobStatus = api_models.JobStatus
    ctx.ProcessRequest = api_models.ProcessRequest
    ctx.HTTPException = HTTPException
    ctx.RASTER_NODATA = raster_settings.RASTER_NODATA
    ctx.UPLOAD_DIR = raster_settings.UPLOAD_DIR
    ctx._INDICATOR_FORMULAS = raster_quality.INDICATOR_FORMULAS
    ctx._quality_from_cloud_pct = raster_quality.quality_from_cloud_pct
    ctx._safe_raster_source = raster_security_context.safe_raster_source
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


def run_processing(job_id: str, req: api_models.ProcessRequest) -> None:
    """Run a single raster processing job without depending on main.py."""
    raster_job_orchestration.run_processing(make_processing_context(), job_id, req)


def run_batch_processing(job_id: str, req: api_models.BatchProcessRequest) -> None:
    """Run a batch raster processing job without depending on main.py."""
    raster_job_orchestration.run_batch_processing(make_processing_context(), job_id, req)
