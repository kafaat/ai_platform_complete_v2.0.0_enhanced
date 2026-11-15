"""Field-router runtime façade without importing main.py.

This adapter exists to finish the staged router decomposition: ``routers/fields.py``
can use the already-extracted modules directly while preserving the legacy helper
names that its endpoint code still expects.
"""

from __future__ import annotations

import functools
import logging
import os
import sys
from datetime import UTC, datetime

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
from anyio import CapacityLimiter, to_thread
from anyio.lowlevel import RunVar
from fastapi import Header, HTTPException

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


def _reject_stale_revision(requested: int | None, current: int | None) -> None:
    """مراجعةٌ في الجسم تخالف المراجعة المخزّنة ⇒ 409 ``stale_geometry_revision`` (عقد T10 واحد)."""
    if requested is not None and requested != current:
        raise HTTPException(
            409,
            {
                "code": "stale_geometry_revision",
                "requested_revision": requested,
                "current_revision": current,
                "message_ar": "مراجعة هندسة الحقل في الطلب ليست المراجعة المخزّنة الحاليّة.",
            },
        )


async def _cdse_request_on_stored_field(
    field_id: str, req: api_models.ProcessCdseRequest, owner: str
) -> api_models.ProcessCdseRequest:
    """هندسة process-cdse ومراجعتها من جدول ``fields`` (مصدر الحقيقة) لا من جسم الطلب (T10).

    هندسة الجسم كانت تُقصّ بها الطبقات وتُحفَظ باسم الحقل، فيُعالَج أيّ مضلّع تحت معرّف
    حقل. مع قاعدة: الهندسة المخزّنة تحكم (وbbox يُشتقّ منها) والجسم يُتجاهَل؛ غيابها ⇒ 400.
    ومراجعتها (``geometry_revision``) تُقرأ معها في جملة واحدة وتُختَم على الطلب: مراجعةُ
    الجسم كانت تبقى فتُحفَظ N نَسَباً لأصلٍ قُصّ بهندسة N+1 (مراجعة PR #1324). مراجعةٌ في
    الجسم تخالف المخزّنة ⇒ 409 ``stale_geometry_revision`` بلا مهمّة، لا خلط نَسَب.
    بلا قاعدة (وضع مقصود، كفحص الملكيّة بالذاكرة) لا سجلّ نقارن به فتبقى هندسة الجسم.
    والمستأجر ``owner`` (مستأجر السياق) يُثبَّت على الطلب فتُنسَب الطبقات لمالكها.
    """
    import db_persist as _dbp

    geometry, bbox, revision = req.geometry, list(req.bbox), req.geometry_revision
    if _dbp.DATABASE_URL:
        try:
            stored = await _dbp.fetch_field_geometry_with_revision(field_id, _REQ_TENANT.get())
        except Exception as e:  # noqa: BLE001 — تعذّر جلب الهندسة ⇒ 503 صادق
            raise HTTPException(503, "تعذّر جلب هندسة الحقل المخزّنة") from e
        geometry = (stored or {}).get("geometry")
        bbox = _bbox_from_geojson(geometry)
        if geometry is None or bbox is None:
            raise HTTPException(400, "هندسة الحقل المخزّنة غير متاحة لمعالجة CDSE")
        revision = stored.get("revision")
        _reject_stale_revision(req.geometry_revision, revision)
        if req.geometry is not None and req.geometry != geometry:
            logger.warning("process-cdse field=%s: body geometry ignored (stored wins)", field_id)
    return req.model_copy(
        update={
            "geometry": geometry,
            "bbox": bbox,
            "geometry_revision": revision,
            "tenant_id": owner,
        }
    )


async def _clip_on_stored_field(field_id: str, req) -> tuple[dict | None, int | None]:
    """مضلّع القصّ **ومراجعته** لـprocess-date/backfill/process-from-stac من ``fields`` (قاعدة T10).

    ``req`` أيّ طلب يحمل ``clip_polygon_geojson`` و``geometry_revision`` (الثلاثة تحملهما).

    مع قاعدة: غياب مضلّع الجسم ⇒ الهندسة المخزّنة؛ مضلّع جسمٍ يُقبَل فقط إن احتوته الهندسة
    المخزّنة (وإلّا 400) — فلا يُقصّ ويُحفَظ باسم الحقل مضلّعٌ يختاره المُنادي؛ غياب المخزّنة ⇒ 400.
    والمراجعة تُقرأ مع الهندسة في جملة واحدة وتُرجَع معها: كانت المراجعة N من الجسم تُجدوَل
    مع هندسة N+1 المخزّنة فيُختَم أصلٌ بنَسَبٍ خاطئ ويُعاد استعمال أصلٍ بمفتاح مراجعةٍ خاطئ
    (مراجعة PR #1330). مراجعة جسمٍ تخالف المخزّنة ⇒ 409 كـprocess-cdse.
    بلا قاعدة (وضع مقصود) لا سجلّ نقارن به فيبقى مضلّع الجسم ومراجعته كما كانا (قد يكونان None).
    """
    import db_persist as _dbp

    body_clip, requested_revision = req.clip_polygon_geojson, req.geometry_revision
    if not _dbp.DATABASE_URL:
        return body_clip, requested_revision
    try:
        stored = await _dbp.fetch_field_geometry_with_revision(field_id, _REQ_TENANT.get())
    except Exception as e:  # noqa: BLE001 — تعذّر جلب الهندسة ⇒ 503 صادق
        raise HTTPException(503, "تعذّر جلب هندسة الحقل المخزّنة") from e
    geometry = (stored or {}).get("geometry")
    if geometry is None or _bbox_from_geojson(geometry) is None:
        raise HTTPException(400, "هندسة الحقل المخزّنة غير متاحة لاشتقاق bbox وقصّ الصور")
    revision = stored.get("revision")
    _reject_stale_revision(requested_revision, revision)
    if not body_clip:
        return geometry, revision
    if not raster_date_geo.clip_within_field(body_clip, geometry):
        raise HTTPException(400, "clip_polygon_geojson يقع خارج هندسة الحقل المخزّنة")
    return body_clip, revision


def _clip_resolvable(req) -> bool:
    """هل سيُحلّ لهذا الطلب مضلّع قصّ؟ — لحارس process-from-stac الذي يسبق فحص المستأجر.

    كان الحارس يفحص ``req.clip_polygon_geojson`` الخام، فيُرفَض 422 ``radiometry_unresolved``
    طلبٌ بلا مضلّع قبل أن يُطبَّق افتراض T10 (الهندسة المخزّنة) — مراجعة #1330. مع قاعدة
    يُرجِع ``_clip_on_stored_field`` دائماً مضلّعاً غير فارغ أو يرفع (400/409/503)، فالقصّ
    محلولٌ حتماً؛ بلا قاعدة يبقى مضلّع الجسم وحده. فيُحكَم على الطلب الموروث مبكّراً بلا قراءة.
    """
    import db_persist as _dbp

    return bool(req.clip_polygon_geojson) or bool(_dbp.DATABASE_URL)


def _cdse_job_record(job_id: str, owner: str, req, gate_decision) -> dict:
    """سجلّ مهمّة process-cdse المعلَّقة، مربوطاً بمستأجِره وبقرار بوّابة satellite_cdse."""
    job_record = {
        "job_id": job_id,
        "tenant_id": owner,
        "status": JobStatus.pending,
        "progress_pct": 0,
        "created_at": datetime.now(UTC).isoformat(),
        "indicators": list(req.indicators),
        "provider": "cdse",
    }
    if gate_decision is not None:
        # Bind the job to the exact activation generation it was authorized under (proof #4/#5):
        # a later revoke/expiry bumps the generation, so the persisted evidence is non-repudiable.
        job_record["gate"] = gate_decision.evidence()
    return job_record


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
    # Same contract as layer_lookup.real_field_grid, but the COG read runs off the loop (R9).
    layer = await _resolve_field_layer(field_id, index, date)
    if layer is None:
        return None
    return await run_raster_io(_grid_from_cog, layer, index, date, grid)


# R9: Blocking raster I/O off the event loop, bounded.
# قراءة GDAL/rasterio متزامنة داخل معالج async على عامل uvicorn واحد كانت تُجمّد الخدمة كلّها
# خلف COG بعيد بطيء. تُنفَّذ في خيط بحدّ تزامن (RASTER_IO_CONCURRENCY) كي لا تستهلك الخيوط
# كلّها؛ والمحدِّد لكلّ حلقة أحداث (RunVar) كمحدِّد anyio الافتراضيّ نفسه.
_RASTER_IO_LIMITER: RunVar[CapacityLimiter] = RunVar("raster_io_limiter")


def raster_io_concurrency() -> int:
    try:
        return max(1, int(os.getenv("RASTER_IO_CONCURRENCY", "8")))
    except ValueError:
        return 8


def _raster_io_limiter() -> CapacityLimiter:
    try:
        return _RASTER_IO_LIMITER.get()
    except LookupError:
        limiter = CapacityLimiter(raster_io_concurrency())
        _RASTER_IO_LIMITER.set(limiter)
        return limiter


async def run_raster_io(func, /, *args, **kwargs):
    """Run a blocking GDAL/rasterio call in a worker thread under the raster I/O limiter."""
    call = functools.partial(func, *args, **kwargs)
    return await to_thread.run_sync(call, limiter=_raster_io_limiter())


def _read_index_pixel(path: str, lon: float, lat: float) -> float | None:
    """Open ``path`` and sample the index pixel (blocking; call via ``run_raster_io``)."""
    import rasterio

    with rasterio.open(path) as src:
        return _sample_index_pixel(src, lon, lat)


class InvalidPixelSource(ValueError):
    """The raster cannot supply a georeferenced scalar measurement."""


def _sample_index_pixel(src, lon: float, lat: float) -> float | None:
    """قيمة بكسل المؤشّر عند (lon, lat) بـEPSG:4326 من راستر مفتوح، أو None إن لم تصلح.

    ``IndexError`` إن وقعت النقطة خارج الراستر. ``masked=True``: القناع الداخليّ للبيانات
    يُبطل البكسل كما يُبطله nodata — بدونه تُرجَع قيمة بكسل مخفيّ كأنّها صالحة (T10).
    """
    import math

    import numpy as np
    from rasterio.enums import ColorInterp
    from rasterio.warp import transform

    if src.crs is None:
        raise InvalidPixelSource("نظام إحداثيات طبقة المؤشر غير معروف")
    if any(band != ColorInterp.alpha for band in src.colorinterp[1:]):
        raise InvalidPixelSource("تتطلب قراءة البكسل طبقة مؤشر أحادية القيم")
    xs, ys = [lon], [lat]
    if str(src.crs).upper() not in ("EPSG:4326", "OGC:CRS84"):
        xs, ys = transform("EPSG:4326", src.crs, xs, ys)
    row, col = src.index(xs[0], ys[0])
    if row < 0 or col < 0 or row >= src.height or col >= src.width:
        raise IndexError("point outside raster")
    value = next(src.sample([(xs[0], ys[0])], masked=True))[0]
    if value is np.ma.masked or (src.nodata is not None and value == src.nodata):
        return None
    return float(value) if math.isfinite(float(value)) else None


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


def tile_asset_revision(
    layer: dict, cog_path: str, date: str, v: str | None
) -> tuple[str, str, bool]:
    """``(resolved_date, version, cacheable)`` for a resolved field tile asset.

    The cache key follows the resolved asset (URI, capture day, revision columns and, for a
    local file, its inode/size/mtime), not the requested date. A remote asset without a
    revision may be overwritten at the same URI, so it is not cacheable.
    """
    import hashlib
    import json

    from raster_available_dates import utc_day

    resolved_date = utc_day(layer.get("acquisition_date")) or date
    revision = [layer.get(key) for key in ("created_at", "processing_job_id", "data_available_at")]
    local = "://" not in cog_path and not cog_path.startswith("/vsi")
    if local:
        try:
            stat = os.stat(cog_path)
            revision.extend((stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns))
        except OSError:
            pass
    identity = json.dumps([layer["cog_url"], resolved_date, *revision, v], default=str)
    return resolved_date, hashlib.sha256(identity.encode()).hexdigest(), local or any(revision)


def tilejson_asset_version(layer: dict | None, date: str, v: str | None) -> tuple[str, str]:
    """``(resolved_date, version)`` advertised by TileJSON for the resolved asset."""
    import hashlib

    from raster_available_dates import utc_day

    asset = layer or {}
    resolved_date = utc_day(asset.get("acquisition_date")) or date
    resolved_version = v or str(asset.get("created_at") or "")
    if not resolved_version:
        uri = asset.get("cog_url")
        resolved_version = hashlib.sha256(uri.encode()).hexdigest() if uri else "default"
    return resolved_date, resolved_version


# Field time series.
def _timeseries_point(real: dict, date: str) -> dict:
    """One ``/v1/fields/{id}/timeseries`` point from a real field grid (no invented values)."""
    provenance = (real.get("indicator_product") or {}).get("provenance") or {}
    return {
        "datetime": str(real.get("date") or date)[:10],
        "mean": real["stats"]["mean"],
        # Measured quality (RS-4) and the grid's own scene lineage (vegetation's
        # /v1/ndvi/current needs it) — None = "not reported", never a fabricated value.
        "valid_pixel_ratio": real.get("valid_pixel_ratio"),
        "coverage_ratio": real.get("coverage_ratio"),
        "cloud_pct": real.get("cloud_pct"),
        "scene_id": provenance.get("scene_id"),
        # S4-a: هويّة الأصل لا الرقم وحده — المشهد نفسه على حدٍّ أحدث للحقل أصلٌ آخر.
        # مراجعة الهندسة من هويّة الشبكة والأصل المقروء من نَسَب المنتج؛ None حين يغيب.
        "geometry_revision": (real.get("grid_identity") or {}).get("geometry_revision"),
        "source_uri": provenance.get("source_uri"),
    }


async def _common_mask_analysis(
    field_id: str, points: list[dict], analysis: dict, min_common_coverage: float
) -> dict:
    """Recompute the field trend over the pixels valid in every scene (``common_mask=true``).

    Each point's source COG is resampled onto one field grid bound to the saved field
    geometry and its revision; see ``time_series.COMMON_MASK_RULE`` for scene exclusion.
    """
    import raster_field_coverage
    import time_series

    geometry = revision = None
    try:
        import db_persist

        saved = await db_persist.fetch_field_geometry_with_revision(field_id, _REQ_TENANT.get())
        if saved:
            geometry, revision = saved.get("geometry"), saved.get("revision")
    except Exception as exc:  # noqa: BLE001 — without the boundary the mask basis is declared
        logger.warning("common mask: field geometry unavailable (%s)", type(exc).__name__)
    scenes = [
        {
            "datetime": p.get("datetime"),
            "scene_id": p.get("scene_id"),
            "geometry_revision": p.get("geometry_revision"),
            "path": object_store.to_gdal_path(p["source_uri"]) if p.get("source_uri") else None,
        }
        for p in points
    ]
    try:
        aligned = await run_raster_io(
            raster_field_coverage.align_scenes_to_field_grid, scenes, geometry, revision
        )
    except Exception as exc:  # noqa: BLE001 — declared as unavailable, never a silent fallback
        logger.warning("common mask: alignment failed (%s)", type(exc).__name__)
        aligned = None
    return time_series.apply_common_mask(
        analysis, points, aligned, min_common_coverage=min_common_coverage
    )
