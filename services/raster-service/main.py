"""raster-service (port 8001) — خدمة الصور الجوّية والراستر لـSAHOOL

تسدّ الفجوة المعماريّة: تطبيق الجوال (imagery.ts + raster.ts) يستدعي هذه
الخدمة على المنفذ 8001، لكنّها لم تكن موجودة. هذه الخدمة تنفّذ العقد كاملاً.

تتّصل بـElement84 Earth Search (STAC) للبحث عن صور Sentinel-2 مجّاناً (بلا
مفتاح)، وتعالج الراستر لحساب المؤشّرات النباتيّة (NDVI/EVI/...) وإنتاج بلاطات
خرائط لـMapLibre.

المسارات (مطابقة لعقد الجوال):
  GET  /imagery/search/recent   — آخر صور Sentinel-2 لمنطقة
  GET  /imagery/search/season   — صور الموسم الزراعي
  GET  /imagery/search/radar    — رادار Sentinel-1 (يخترق الغيوم)
  POST /imagery/search          — بحث متقدّم
  POST /upload/raster           — رفع راستر
  POST /upload/drone            — رفع أورثوموزاييك درون
  POST /process                 — معالجة مؤشّر (غير متزامن → job)
  GET  /jobs/{job_id}           — حالة المهمّة
  GET  /jobs/{job_id}/result    — نتيجة المهمّة
  GET  /info/{layer_id}         — معلومات طبقة راستر
  GET  /tiles/{layer_id}/{z}/{x}/{y}.png — بلاطة خريطة
  GET  /healthz /readyz         — فحوص الصحّة

المرجع المُحقَّق:
  Element84 Earth Search v1 — https://earth-search.aws.element84.com/v1
  Sentinel-2 L2A مجّاني (AWS Open Data)، إعادة زيارة ٥ أيّام.

⚠ معالجة الراستر الفعليّة (rasterio/GDAL) تحتاج مكتبات ثقيلة. هذه الخدمة
تنفّذ البنية والعقد كاملاً؛ المعالجة الفعليّة للبكسلات تتمّ عند توفّر
rasterio في بيئة التشغيل (تُحقن في process_raster_job). البحث عن الصور
(STAC) يعمل بالكامل بـhttpx دون مكتبات ثقيلة.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import band_math
import object_store
import raster_settings

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from stac_client import ResilientStacClient

try:
    from shared.logging_config import setup_logging

    logger = setup_logging("raster-service")
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","svc":"raster-service","msg":"%(message)s"}',
    )
    logger = logging.getLogger("raster-service")

# ─── الإعداد ──────────────────────────────────────────────────────
# Phase 11 decomposition: runtime constants moved to raster_settings.py.
# Re-export legacy names from main.py for routers/tests and staged ctx-based helpers.
EARTH_SEARCH_URL = raster_settings.EARTH_SEARCH_URL
CORS_ORIGINS = raster_settings.CORS_ORIGINS
HTTP_TIMEOUT = raster_settings.HTTP_TIMEOUT
TITILER_URL = raster_settings.TITILER_URL
_fallback_chain = raster_settings.stac_fallback_chain()

_stac = ResilientStacClient(
    EARTH_SEARCH_URL,
    timeout=HTTP_TIMEOUT,
    max_retries=int(os.getenv("STAC_MAX_RETRIES", "3")),
    cache_ttl=float(os.getenv("STAC_CACHE_TTL", "900")),
    redis_url=os.getenv("REDIS_URL"),  # None → ذاكرة فقط (تدهور لطيف)
    fallback_urls=_fallback_chain,
)


# ─── API models / enums ─────────────────────────────────────────────
# Extracted from main.py; re-exported for backward compatibility with routers,
# workers, and tests that import symbols from main during staged decomposition.
from raster_api_models import (  # noqa: E402
    AutoBackfillPolicy,
    BACKFILL_PRESET_MONTHS as _BACKFILL_PRESET_MONTHS,
    BandMapping,
    BatchProcessRequest,
    GeoParquetExportRequest,
    HistoricalBackfillPreset,
    HistoricalBackfillRequest,
    IndicatorKind,
    JobStatus,
    MosaicPlanRequest,
    ProcessRequest,
    SceneCandidate,
    SceneRankRequest,
    SearchRequest,
    SourceFormat,
)

# ─── Scene ranking / historical backfill selection policy ─────────────
# Extracted from main.py; re-exported under legacy names so routers/tests/workers
# that import main._scene_* keep working without behavior drift.
# صيانة كاش البلاطات (تعقيم المسار + الإبطال + الإخلاء) في وحدة مستقلّة بلا FastAPI
# كي يستوردها عامل الإبطال بخفّة وتُختبَر بمعزل. نُعيد تصديرها هنا للتوافق.
import tile_cache_maint  # noqa: E402

invalidate_field_tile_cache = tile_cache_maint.invalidate_field_tile_cache
prune_tile_cache = tile_cache_maint.prune_tile_cache


# Phase 10 decomposition: tile/tilejson counters moved to tile_observability.py.
# Keep legacy main._TILE_OBS/main._obs_inc symbols for routers/tests.
import tile_observability  # noqa: E402

_TILE_OBS = tile_observability.TILE_OBS
_TILE_OBS_BY_INDEX = tile_observability.TILE_OBS_BY_INDEX
_obs_inc = tile_observability.obs_inc


# ─── Date-window and GeoJSON helpers ────────────────────────────────
import raster_date_geo  # noqa: E402

_parse_ymd = raster_date_geo.parse_ymd
_bbox_from_geojson = raster_date_geo.bbox_from_geojson
_month_windows = raster_date_geo.month_windows


def _backfill_date_range(req: HistoricalBackfillRequest) -> tuple[datetime, datetime, int]:
    return raster_date_geo.backfill_date_range(req, _BACKFILL_PRESET_MONTHS)


def _scene_band_mapping(bands: dict[str, str]) -> BandMapping:
    keys = ["blue", "green", "red", "nir", "rededge", "swir1", "swir2", "scl"]
    return BandMapping(**{k: i + 1 for i, k in enumerate(keys) if bands.get(k)})


# ─── حالة المهامّ والطبقات ─────────────────────────────────────────
# Phase 12 decomposition: mutable runtime registries moved to raster_runtime_state.py.
# Keep legacy main._jobs/_layers/_field_layers aliases while routers migrate gradually.
import raster_runtime_state  # noqa: E402

_jobs = raster_runtime_state.JOBS
_layers = raster_runtime_state.LAYERS
_field_layers = raster_runtime_state.FIELD_LAYERS

# v11-F3/F5: layer cache eviction moved to layer_cache_events.py.
# Compatibility wrappers preserve main._evict_field_layers/main._layer_evict_subscriber.
import layer_cache_events  # noqa: E402

_LAYER_EVICT_CHANNEL = layer_cache_events.DEFAULT_LAYER_EVICT_CHANNEL


def _layer_evict_enabled() -> bool:
    return layer_cache_events.layer_evict_enabled()


def _evict_field_layers(field_id: str) -> int:
    return layer_cache_events.evict_field_layers(
        field_id,
        layers=_layers,
        field_layers=_field_layers,
        logger=logger,
    )


async def _layer_evict_subscriber() -> None:
    return await layer_cache_events.layer_evict_subscriber(
        layers=_layers,
        field_layers=_field_layers,
        logger=logger,
        redis_url=os.getenv("REDIS_URL"),
        channel=_LAYER_EVICT_CHANNEL,
    )


# ─── بحث الصور عبر STAC/CDSE ──────────────────────────────────────
import stac_search as stac_search_helpers

stac_search_helpers.configure(
    stac=_stac,
    logger=logger,
    earth_search_url=EARTH_SEARCH_URL,
    http_timeout=HTTP_TIMEOUT,
    historical_search_provider=raster_settings.HISTORICAL_SEARCH_PROVIDER,
    sentinel_collection=raster_settings.SENTINEL_COLLECTION,
    sentinel1_collection=raster_settings.SENTINEL1_COLLECTION,
    landsat_collection=raster_settings.LANDSAT_COLLECTION,
    dem_collection=raster_settings.DEM_COLLECTION,
    landsat_unique_indices=raster_settings.LANDSAT_UNIQUE_INDICES,
    landsat_direct_raster_indices=raster_settings.LANDSAT_DIRECT_RASTER_INDICES,
    landsat_derived_indices=raster_settings.LANDSAT_DERIVED_INDICES,
    landsat_duplicate_sentinel_indices=raster_settings.LANDSAT_DUPLICATE_SENTINEL_INDICES,
    landsat_thermal_asset_candidates=raster_settings.LANDSAT_THERMAL_ASSET_CANDIDATES,
)

# Compatibility façade: routers/tests still import these helpers from main.py.
_band_urls_from_assets = stac_search_helpers.band_urls_from_assets
_stac_query = stac_search_helpers.stac_query
_stac_search = stac_search_helpers.stac_search
_stac_search_cdse = stac_search_helpers.stac_search_cdse
_stac_search_element84 = stac_search_helpers.stac_search_element84
_stac_search_radar = stac_search_helpers.stac_search_radar
_landsat_thermal_href = stac_search_helpers.landsat_thermal_href
_stac_search_landsat = stac_search_helpers.stac_search_landsat
_stac_search_landsat_unique = stac_search_helpers.stac_search_landsat_unique
_stac_search_dem = stac_search_helpers.stac_search_dem


import raster_backfill_scene_processing  # noqa: E402


def _process_backfill_scene_cdse(
    scene: dict,
    index: str,
    field_id: str,
    tenant_id: str | None,
    clip: dict | None,
    geometry_revision,
    jid: str,
) -> None:
    ctx = raster_processing_runtime.make_processing_context(upload_dir=UPLOAD_DIR)
    ctx._bbox_from_geojson = raster_date_geo.bbox_from_geojson
    return raster_backfill_scene_processing.process_backfill_scene_cdse(
        ctx, scene, index, field_id, tenant_id, clip, geometry_revision, jid
    )


# ─── lifespan + التطبيق ───────────────────────────────────────────
# Phase 10 decomposition: lifecycle/startup wiring moved to raster_app_lifecycle.py.
import raster_app_lifecycle  # noqa: E402

lifespan = raster_app_lifecycle.make_lifespan(
    logger=logger,
    object_store_module=object_store,
    database_url_getter=lambda: os.getenv("DATABASE_URL", ""),
    layer_evict_enabled=_layer_evict_enabled,
    layer_evict_subscriber=_layer_evict_subscriber,
)


app = FastAPI(title="SAHOOL Raster Service", version="9.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-Id"],
    allow_credentials=True,
)


# ─── سياق المستأجِر/تفويض الطبقات/حراسة المصادر ─────────────────────
# Phase 9 decomposition: security/tenant/source helpers moved to raster_security_context.py.
# Compatibility wrappers below preserve main._* symbols used by routers/tests.
import raster_security_context  # noqa: E402

_REQ_TENANT = raster_security_context.REQ_TENANT


def _tenant_from_header(value: str | None) -> str | None:
    return raster_security_context.tenant_from_header(value)


def _tenant_from_request(request) -> str | None:
    return raster_security_context.tenant_from_request(request)


@app.middleware("http")
async def _tenant_context_mw(request, call_next):
    token = _REQ_TENANT.set(_tenant_from_request(request))
    try:
        return await call_next(request)
    finally:
        _REQ_TENANT.reset(token)


_field_owner = raster_security_context.field_owner
_field_owner_cache = raster_security_context._field_owner_cache


async def _require_field_tenant(field_id: str, *, hide_existence: bool = False) -> None:
    return await raster_security_context.require_field_tenant(
        field_id,
        hide_existence=hide_existence,
        layers=_layers,
        field_layers=_field_layers,
        logger=logger,
        owner_lookup=_field_owner,
    )


def _require_layer_tenant(layer_id: str) -> None:
    return raster_security_context.require_layer_tenant(layer_id, layers=_layers)


async def _require_layer_tenant_authorized(layer_id: str) -> None:
    return await raster_security_context.require_layer_tenant_authorized(
        layer_id, layers=_layers, logger=logger
    )


_public_cog_url = raster_security_context.public_cog_url

# ─── مسارات بحث الصور (public_catalog: بحث صور أقمار عامّة بـbbox — لا بيانات مستأجِر) ──


from raster_api_models import (  # noqa: E402
    ChangeDetectRequest,
    FvcComputeRequest,
    ManagementZonesRequest,
    MAX_CHANGE_GRID_CELLS,
    SarRviRequest,
    TerrainRequest,
    TimeSeriesAnalyzeRequest,
)


# ─── الفحوص ───────────────────────────────────────────────────────


# ─── معالجة الراستر: الرفع ────────────────────────────────────────
UPLOAD_DIR = raster_settings.UPLOAD_DIR
_SSRF_BLOCKED_HOSTS = raster_settings.SSRF_BLOCKED_HOSTS


def _safe_raster_source(url: str | None) -> str:
    return raster_security_context.safe_raster_source(url, UPLOAD_DIR, _SSRF_BLOCKED_HOSTS)


# مصادقة خدمة-لخدمة: رفع الراستر يكتب ملفّات — منع إساءة التخزين/الحقن
AGENT_TOKEN = raster_settings.AGENT_TOKEN


def _require_service_token(x_agent_token: str = Header(None)) -> None:
    return raster_security_context.require_service_token(x_agent_token, AGENT_TOKEN)


os.makedirs(UPLOAD_DIR, exist_ok=True)


# ─── المعالجة غير المتزامنة (job) ─────────────────────────────────
# Phase 9 decomposition: formulas and quality helpers moved to raster_quality.py.
import raster_quality  # noqa: E402

_INDICATOR_FORMULAS = raster_quality.INDICATOR_FORMULAS
_quality_from_cloud_pct = raster_quality.quality_from_cloud_pct
_pixel_quality = raster_quality.pixel_quality


# Persistence helpers are implemented outside main.py; keep private aliases here
# for existing tests and routers that still import from main during the staged split.
from raster_asset_persistence import persist_raster_asset as _persist_raster_asset  # noqa: E402
import raster_processing_runtime  # noqa: E402


def _run_processing(job_id: str, req: ProcessRequest):
    """Compatibility wrapper backed by an explicit processing context."""
    return raster_processing_runtime.run_processing(job_id, req, upload_dir=UPLOAD_DIR)


def _run_batch_processing(job_id: str, req: BatchProcessRequest):
    """Compatibility wrapper backed by an explicit processing context."""
    return raster_processing_runtime.run_batch_processing(job_id, req, upload_dir=UPLOAD_DIR)


def _process_precomputed_pixels(req: ProcessRequest, layer_id: str):
    """Compatibility wrapper backed by an explicit processing context."""
    return raster_processing_runtime.process_precomputed_pixels(
        req, layer_id, upload_dir=UPLOAD_DIR
    )


def _process_precomputed_truecolor(req: ProcessRequest):
    """Compatibility wrapper backed by an explicit processing context."""
    return raster_processing_runtime.process_precomputed_truecolor(req, upload_dir=UPLOAD_DIR)


def _process_pixels(req: ProcessRequest, layer_id: str):
    """Compatibility wrapper backed by an explicit processing context."""
    return raster_processing_runtime.process_pixels(req, layer_id, upload_dir=UPLOAD_DIR)


from raster_api_models import ProcessCdseRequest, ProcessFromStacRequest  # noqa: E402


import raster_cdse_processing  # noqa: E402


def _run_cdse_processing(job_id: str, field_id: str, req: ProcessCdseRequest):
    """Compatibility wrapper backed by an explicit processing context."""
    ctx = raster_processing_runtime.make_processing_context(upload_dir=UPLOAD_DIR)
    return raster_cdse_processing.run_cdse_processing(ctx, job_id, field_id, req)


# Transparent fallback PNG and finite nodata moved to raster_settings.py.
_TRANSPARENT_PNG = raster_settings.TRANSPARENT_PNG
RASTER_NODATA = raster_settings.RASTER_NODATA


# ─── دورة حياة الراستر (سدّ فجوة: لا سياسة تنظيف) ──────────────────────


# ─── حزم offline (MBTiles) للمناطق ضعيفة الاتّصال — سدّ فجوة اليمن ──────
OFFLINE_PACKS_DIR = raster_settings.OFFLINE_PACKS_DIR
os.makedirs(OFFLINE_PACKS_DIR, exist_ok=True)


# ─── (٥) شبكة المؤشّر لكلّ بكسل (per-pixel grid) للموبايل ──────────────
# Phase 3 decomposition: layer lookup/grid/RVI helpers moved to layer_lookup.py.
# Compatibility wrappers below preserve the public main._* symbols used by routers/tests.
import layer_lookup  # noqa: E402

_GRID_INDEX_ALIASES = layer_lookup.GRID_INDEX_ALIASES


def _normalize_index(index: str | None) -> str:
    return layer_lookup.normalize_index(index)


def _display_index(index: str | None) -> str:
    return layer_lookup.display_index(index)


def _find_field_layer(field_id: str, index: str, date: str) -> dict | None:
    return layer_lookup.find_field_layer(_layers, _field_layers, field_id, index, date)


def _grid_from_cog(layer: dict, index: str, date: str, grid: int) -> dict | None:
    return layer_lookup.grid_from_cog(layer, index, date, grid, object_store)


async def _rehydrate_field_layer_from_db(field_id: str, internal: str, date: str) -> dict | None:
    return await layer_lookup.rehydrate_field_layer_from_db(
        field_id,
        internal,
        date,
        layers=_layers,
        field_layers=_field_layers,
        tenant_getter=_REQ_TENANT.get,
        logger=logger,
        object_store_module=object_store,
    )


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


async def _rvi_from_sar_cog(field_id: str, date: str) -> float | None:
    return await layer_lookup.rvi_from_sar_cog(
        field_id,
        date,
        layers=_layers,
        field_layers=_field_layers,
        tenant_getter=_REQ_TENANT.get,
        logger=logger,
        object_store_module=object_store,
    )


from raster_api_models import FieldChangeRequest, PrescriptionRequest  # noqa: E402


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


# ─── السلسلة الزمنيّة للمؤشّر (field-scoped) ──────────────────────────


# ─── بلاطات XYZ ديناميكيّة (TiTiler-style) من COG الحقل المقصوص ────────


# ─── معايرة الملوحة (البند ٢) ────────────────────────────────────
from raster_api_models import SalinityClassifyRequest, SalinityFitRequest  # noqa: E402


# ─── Cloud-native GIS/STAC facade (Phase 4 inspired by TiTiler/Terracotta/OGC) ───


# ════════════════════════════════════════════════════════════════════
# توحيد main↔cert (Stage B): تفعيل بلاطات CDSE الحيّة (poly clip) من main
# ════════════════════════════════════════════════════════════════════
# cert تفرّع قبل مسار cdse-tiles؛ بنيته التحتيّة لـCDSE موجودة هنا
# (_run_cdse_processing/ProcessCdseRequest/_jobs/…) عدا مساعِدات للكاش/القفل.
# نُبقي واجهة main._cdse_* للتوافق، لكن الحالة والمنطق صارا في وحدة صغيرة قابلة للاختبار.
import cdse_singleflight  # noqa: E402

_cdse_tile_cache = cdse_singleflight.cdse_tile_cache
_cdse_key_locks = cdse_singleflight.cdse_key_locks
_cdse_lock = cdse_singleflight.cdse_lock
_cdse_key_lock = cdse_singleflight.cdse_key_lock
_cdse_prune_key_locks_locked = cdse_singleflight.cdse_prune_key_locks_locked


def _bbox_from_geom(geom: dict | None) -> list[float] | None:
    return raster_date_geo.bbox_from_geom(geom)


# ════════════════════════════════════════════════════════════════════
# تسجيل تلقائيّ لكلّ راوترات routers/ (تفكيك main.py محفوظ السلوك). يُستدعى في
# نهاية الملفّ بعد تعريف app وكلّ التبعيّات المشتركة (مساعِدات/نماذج/حالة/مساعِدات
# CDSE). الراوترات لا تعتمد على main.*؛ تُسجَّل هنا فقط لربط FastAPI.
# يضمّ register_routers أيضاً routers/cdse_tiles.py تلقائيّاً (لا تضمين يدويّ).
from router_registry import register_routers  # noqa: E402

register_routers(app)
