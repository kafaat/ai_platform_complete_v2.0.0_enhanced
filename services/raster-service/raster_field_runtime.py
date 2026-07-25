"""Field-router runtime façade without importing main.py.

This adapter exists to finish the staged router decomposition: ``routers/fields.py``
can use the already-extracted modules directly while preserving the legacy helper
names that its endpoint code still expects.
"""

from __future__ import annotations

import logging
import os
import sys

import layer_lookup
import object_store
import raster_api_models as api_models
import raster_backfill_scene_processing
import raster_cdse_processing
import raster_date_geo
import raster_processing_runtime
import raster_quality
import raster_runtime_state
import raster_security_context
import raster_settings
import scene_policy
import stac_search as stac_search_helpers
import tile_cache_io
import tile_cache_maint
import tile_observability
from fastapi import Header

logger = logging.getLogger("raster-service")

# API models/enums re-exported for router type hints and object construction.
IndicatorKind = api_models.IndicatorKind
SourceFormat = api_models.SourceFormat
JobStatus = api_models.JobStatus
BandMapping = api_models.BandMapping
ProcessRequest = api_models.ProcessRequest
ProcessFromStacRequest = api_models.ProcessFromStacRequest
ProcessCdseRequest = api_models.ProcessCdseRequest
HistoricalBackfillRequest = api_models.HistoricalBackfillRequest
ProcessDateRequest = api_models.ProcessDateRequest
GeoParquetExportRequest = api_models.GeoParquetExportRequest
PrescriptionRequest = api_models.PrescriptionRequest
FieldChangeRequest = api_models.FieldChangeRequest

# Runtime registries.
_jobs = raster_runtime_state.JOBS
_layers = raster_runtime_state.LAYERS
_field_layers = raster_runtime_state.FIELD_LAYERS

# Settings / constants.


def _upload_dir() -> str:
    main_mod = sys.modules.get("main")
    return getattr(main_mod, "UPLOAD_DIR", raster_settings.UPLOAD_DIR)


UPLOAD_DIR = raster_settings.UPLOAD_DIR
TITILER_URL = raster_settings.TITILER_URL
SENTINEL_COLLECTION = raster_settings.SENTINEL_COLLECTION
LANDSAT_UNIQUE_INDICES = raster_settings.LANDSAT_UNIQUE_INDICES
LANDSAT_DIRECT_RASTER_INDICES = raster_settings.LANDSAT_DIRECT_RASTER_INDICES
LANDSAT_DERIVED_INDICES = raster_settings.LANDSAT_DERIVED_INDICES
LANDSAT_DUPLICATE_SENTINEL_INDICES = raster_settings.LANDSAT_DUPLICATE_SENTINEL_INDICES
_TRANSPARENT_PNG = raster_settings.TRANSPARENT_PNG

# Backfill scene selection policy.
NDVI_PULL_MIN_CLEAR_PCT = scene_policy.NDVI_PULL_MIN_CLEAR_PCT
NDVI_HIGH_QUALITY_CLEAR_PCT = scene_policy.NDVI_HIGH_QUALITY_CLEAR_PCT
NDVI_PULL_MIN_SPACING_DAYS = scene_policy.NDVI_PULL_MIN_SPACING_DAYS
NDVI_PULL_TARGET_SPACING_DAYS = scene_policy.NDVI_PULL_TARGET_SPACING_DAYS
_select_backfill_scenes_by_policy = scene_policy.select_backfill_scenes_by_policy

# Security / tenancy helpers.
_REQ_TENANT = raster_security_context.REQ_TENANT
_public_cog_url = raster_security_context.public_cog_url


def _require_service_token(x_agent_token: str | None = Header(None)) -> None:
    main_mod = sys.modules.get("main")
    token = getattr(main_mod, "AGENT_TOKEN", raster_settings.AGENT_TOKEN)
    raster_security_context.require_service_token(x_agent_token, token)


async def _require_field_tenant(field_id: str, *, hide_existence: bool = False) -> None:
    main_mod = sys.modules.get("main")
    owner_lookup = getattr(main_mod, "_field_owner", None)
    await raster_security_context.require_field_tenant(
        field_id,
        hide_existence=hide_existence,
        layers=_layers,
        field_layers=_field_layers,
        logger=logger,
        owner_lookup=owner_lookup,
    )


def _safe_raster_source(url: str | None) -> str:
    return raster_security_context.safe_raster_source(
        url,
        upload_dir=_upload_dir(),
        blocked_hosts=raster_settings.SSRF_BLOCKED_HOSTS,
    )


# Date/geometry helpers.
_bbox_from_geojson = raster_date_geo.bbox_from_geojson
_month_windows = raster_date_geo.month_windows


def _backfill_date_range(req: api_models.HistoricalBackfillRequest):
    return raster_date_geo.backfill_date_range(req, api_models.BACKFILL_PRESET_MONTHS)


# STAC helpers.


async def _stac_search(bbox, dt_start, dt_end, max_cloud, limit):
    main_mod = sys.modules.get("main")
    patched = getattr(main_mod, "_stac_search", None)
    if patched is not None and patched is not _stac_search:
        return await patched(bbox, dt_start, dt_end, max_cloud, limit)
    return await stac_search_helpers.stac_search(bbox, dt_start, dt_end, max_cloud, limit)


async def _stac_search_landsat_unique(bbox, dt_start, dt_end, max_cloud, limit):
    main_mod = sys.modules.get("main")
    patched = getattr(main_mod, "_stac_search_landsat_unique", None)
    if patched is not None and patched is not _stac_search_landsat_unique:
        return await patched(bbox, dt_start, dt_end, max_cloud, limit)
    return await stac_search_helpers.stac_search_landsat_unique(
        bbox, dt_start, dt_end, max_cloud, limit
    )


# Layer/grid helpers.
_normalize_index = layer_lookup.normalize_index
_display_index = layer_lookup.display_index


def _grid_from_cog(layer: dict, index: str, date: str, grid: int) -> dict | None:
    return layer_lookup.grid_from_cog(layer, index, date, grid, object_store)


async def _resolve_field_layer(field_id: str, index: str, date: str) -> dict | None:
    return await layer_lookup.resolve_field_layer(
        field_id,
        index,
        date,
        layers=_layers,
        field_layers=_field_layers,
        tenant_getter=_REQ_TENANT.get,
        logger=logger,
        object_store_module=object_store,
    )


async def _real_field_grid(field_id: str, index: str, date: str, grid: int) -> dict | None:
    return await layer_lookup.real_field_grid(
        field_id,
        index,
        date,
        grid,
        layers=_layers,
        field_layers=_field_layers,
        tenant_getter=_REQ_TENANT.get,
        logger=logger,
        object_store_module=object_store,
    )


# Tile cache helpers.
def _tile_cache_enabled() -> bool:
    return os.getenv("TILE_CACHE_ENABLED", "true").lower() == "true"


def _tile_cache_key(
    field_id: str,
    index: str,
    date: str,
    z: int,
    x: int,
    y: int,
    tenant_id: str | None,
    v: str | None = None,
) -> str:
    return tile_cache_io.tile_cache_key(
        _upload_dir(),
        tile_cache_maint.safe_cache_segment,
        field_id,
        index,
        date,
        z,
        x,
        y,
        tenant_id,
        v,
    )


def _read_tile_cache(path: str) -> bytes | None:
    return tile_cache_io.read_tile_cache(path, enabled=_tile_cache_enabled())


def _write_tile_cache(path: str, data: bytes) -> None:
    try:
        tile_cache_io.write_tile_cache(path, data, enabled=_tile_cache_enabled())
    except OSError as exc:
        logger.warning("tile cache write skipped: %s", type(exc).__name__)


# Quality/observability.
_pixel_quality = raster_quality.pixel_quality
_obs_inc = tile_observability.obs_inc


# Job runners.
def _run_processing(job_id: str, req: api_models.ProcessRequest) -> None:
    main_mod = sys.modules.get("main")
    patched = getattr(main_mod, "_run_processing", None)
    if patched is not None and patched is not _run_processing:
        return patched(job_id, req)
    return raster_processing_runtime.run_processing(job_id, req)


def _run_cdse_processing(job_id: str, field_id: str, req: api_models.ProcessCdseRequest) -> None:
    ctx = raster_processing_runtime.make_processing_context()
    ctx.IndicatorKind = api_models.IndicatorKind
    ctx.SourceFormat = api_models.SourceFormat
    ctx.BandMapping = api_models.BandMapping
    ctx._rank_scenes = scene_policy.rank_scenes
    ctx._bbox_from_geojson = raster_date_geo.bbox_from_geojson
    raster_cdse_processing.run_cdse_processing(ctx, job_id, field_id, req)


def _process_backfill_scene_cdse(
    scene: dict,
    index: str,
    field_id: str,
    tenant_id: str | None,
    clip: dict | None,
    geometry_revision,
    jid: str,
) -> None:
    ctx = raster_processing_runtime.make_processing_context()
    ctx.IndicatorKind = api_models.IndicatorKind
    ctx.SourceFormat = api_models.SourceFormat
    ctx.BandMapping = api_models.BandMapping
    ctx._bbox_from_geojson = raster_date_geo.bbox_from_geojson
    raster_backfill_scene_processing.process_backfill_scene_cdse(
        ctx, scene, index, field_id, tenant_id, clip, geometry_revision, jid
    )
