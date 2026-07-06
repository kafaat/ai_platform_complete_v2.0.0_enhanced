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

import hmac
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlparse

import band_math
import object_store

# توحيد main↔cert: إعادة تصدير أصناف غيوم SCL من المصدر الوحيد (cdse_client) كي تبقى
# متاحة عبر ``main.SCL_CLOUD_CLASSES`` (يطابقها حارس test_cloud_masking — تماسُك معالجة
# CDSE↔Element84). المصدر الوحيد في cdse_client يمنع انحراف القيم.
from cdse_client import SCL_CLOUD_CLASSES  # noqa: E402
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from job_store import JobStore
from pydantic import BaseModel, Field
from stac_client import ResilientStacClient

# توحيد main↔cert: استعادة دالّة نسبة الغيوم النقيّة + عتبتها (كانتا في main وفُقِدتا حين
# أُخِذت نسخة raster الخاصّة بـcert في الدمج التأسيسيّ). يطابقهما حارس test_cloud_masking.
CLOUD_PCT_WARN_THRESHOLD = float(os.getenv("CLOUD_PCT_WARN_THRESHOLD", "20"))


def compute_cloud_pct(scl, np) -> float | None:
    """نسبة غيوم المشهد من نطاق SCL — دالّة نقيّة قابلة للاختبار بلا rasterio.

    = (عدد بكسلات أصناف الغيوم في ``SCL_CLOUD_CLASSES``) ÷ (عدد بكسلات SCL
    الصالحة، أي ≠ 0 صنف لا-بيانات) × 100. تُرجِع ``None`` إن لم توجد بكسلات
    صالحة (لتفادي القسمة على صفر) أو إن كان ``scl`` فارغاً.
    """
    if scl is None:
        return None
    valid = scl != 0  # SCL=0 ⇒ NO_DATA (مستبعَد من المقام).
    valid_count = int(valid.sum())
    if valid_count == 0:
        return None
    cloud_count = int(np.isin(scl, SCL_CLOUD_CLASSES).sum())
    return cloud_count / valid_count * 100.0


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
EARTH_SEARCH_URL = os.getenv("EARTH_SEARCH_URL", "https://earth-search.aws.element84.com/v1")
# مزوّد البحث التاريخيّ عن مشاهد Sentinel-2: الافتراض "cdse" (Copernicus Data Space
# Ecosystem — كتالوج Sentinel Hub) — التحويل الكامل بعيداً عن Element84 Earth Search
# لطبقة البحث التاريخيّ (المعالجة على CDSE أصلاً). "element84" يبقى ارتداداً صريحاً
# فقط (dev بلا اعتمادات CDSE، أو مجموعات لا يوفّرها CDSE كـرادار/Landsat/DEM).
HISTORICAL_SEARCH_PROVIDER = os.getenv("HISTORICAL_SEARCH_PROVIDER", "cdse").strip().lower()
SENTINEL_COLLECTION = "sentinel-2-l2a"
SENTINEL1_COLLECTION = "sentinel-1-grd"  # رادار SAR — يخترق الغيوم والليل
LANDSAT_COLLECTION = "landsat-c2-l2"  # Landsat C2 L2 — أرشيف 40+ سنة (تكميلي)
# Landsat في Sahool ليس بديلاً لمؤشّرات Sentinel-2 النباتية. نستخدمه فقط للميزة
# الفريدة: الطبقة الحرارية/التاريخ الطويل. لا نكرّر NDVI/NDMI/MSI/SAVI... من Landsat
# إلا إن فُتح مسار بحثي لاحق صراحةً.
LANDSAT_UNIQUE_INDICES = {"lst", "cwsi", "tvdi", "tci", "vhi", "et_inputs"}
LANDSAT_DIRECT_RASTER_INDICES = {"lst"}
LANDSAT_DERIVED_INDICES = {"cwsi", "tvdi", "tci", "vhi", "et_inputs"}
LANDSAT_DUPLICATE_SENTINEL_INDICES = {
    "ndvi",
    "ndmi",
    "msi",
    "ndwi",
    "ndsi",
    "savi",
    "evi",
    "gndvi",
    "ndre",
    "msavi",
    "bsi",
    "bi",
    "bi2",
    "ndti",
    "dbsi",
    "satvi",
    "truecolor",
    "falsecolor",
}
LANDSAT_THERMAL_ASSET_CANDIDATES = (
    "lwir11",
    "surface_temperature",
    "st",
    "st_b10",
    "tir",
    "thermal",
    "thermal_ir",
)
DEM_COLLECTION = "cop-dem-glo-30"  # Copernicus DEM 30م — ارتفاع/انحدار/صرف
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30"))
# خادم بلاطات COG ديناميكي (TiTiler) — سدّ فجوة P0. فارغ = البلاطات الثابتة.
TITILER_URL = os.getenv("TITILER_URL", "")

# عميل STAC مرن (تحسين قلب النظام): إعادة محاولة + cache (Redis مشترك +
# ذاكرة fallback) + مصدر احتياطي + stale-if-error. TTL قابل للضبط.
# المصدر الاحتياطي الأوّل: Microsoft Planetary Computer (STAC عامّ، بحث مجهول).
# نفس بنية STAC، فيعمل بنفس payload عند تعذّر Element84.
PC_STAC_URL = os.getenv(
    "PLANETARY_COMPUTER_URL", "https://planetarycomputer.microsoft.com/api/stac/v1"
)
# مصدر احتياطي ثانٍ (اختياري): Digital Earth Africa — يغطّي أفريقيا فقط.
# اليمن خارج تغطيته، لذا معطّل افتراضيّاً؛ يُفعَّل لمناطق أفريقيّة (القرن الأفريقي).
DEAFRICA_STAC_URL = os.getenv("DEAFRICA_STAC_URL", "https://explorer.digitalearth.africa/stac")

_fallback_chain = []
if os.getenv("STAC_FALLBACK_ENABLED", "true") == "true":
    _fallback_chain.append(PC_STAC_URL)
if os.getenv("DEAFRICA_ENABLED", "false") == "true":  # معطّل افتراضيّاً (اليمن)
    _fallback_chain.append(DEAFRICA_STAC_URL)

_stac = ResilientStacClient(
    EARTH_SEARCH_URL,
    timeout=HTTP_TIMEOUT,
    max_retries=int(os.getenv("STAC_MAX_RETRIES", "3")),
    cache_ttl=float(os.getenv("STAC_CACHE_TTL", "900")),
    redis_url=os.getenv("REDIS_URL"),  # None → ذاكرة فقط (تدهور لطيف)
    fallback_urls=_fallback_chain,
)


# ─── النماذج (مطابقة لأنواع الجوال) ───────────────────────────────
class IndicatorKind(StrEnum):
    ndvi = "ndvi"
    evi = "evi"
    savi = "savi"
    ndwi = "ndwi"
    ndmi = "ndmi"
    gndvi = "gndvi"
    fapar = "fapar"
    vari = "vari"
    gli = "gli"
    tgi = "tgi"
    ndre = "ndre"
    reci = "reci"  # Red-edge chlorophyll index — تحليل متقدم عند الطلب
    gci = "gci"  # Green chlorophyll index
    arvi = "arvi"  # Atmospherically resistant vegetation index
    sipi = "sipi"  # Structure insensitive pigment index
    nbr = "nbr"  # Normalized burn/residue ratio (NIR/SWIR2)
    ccci = "ccci"  # Canopy chlorophyll content index (NDRE/NDVI)
    msi = "msi"  # NDRE (نيتروجين/red-edge) + MSI (إجهاد مائي)
    msavi = "msavi"  # Modified SAVI (تصحيح تربة ذاتي L) — كثافة نباتيّة منخفضة
    moisture = "moisture"  # مؤشّر رطوبة (NDMI-style: NIR/SWIR1) للواجهة
    # مؤشّرات التربة (Sentinel-2) — تسدّ نقص: السابقة كلّها نباتيّة
    bsi = "bsi"
    bi = "bi"
    bi2 = "bi2"
    ndti = "ndti"
    dbsi = "dbsi"
    ndsi = "ndsi"
    satvi = "satvi"
    # Landsat-only thermal unique layer. LST is the direct raster product; CWSI/TVDI/TCI/VHI
    # are derived downstream from LST + weather/NDVI history, not fetched as duplicate optical indices.
    lst = "lst"
    cwsi = "cwsi"
    tvdi = "tvdi"
    tci = "tci"
    vhi = "vhi"
    et_inputs = "et_inputs"
    # الصورة الخام بالألوان الطبيعيّة (RGBA UINT8) — ليست مؤشّراً أحاديّ النطاق؛ تُصيَّر
    # وتُحفَظ كـCOG متعدّد النطاقات (مسار precomputed truecolor). لا صيغة band-math لها.
    truecolor = "truecolor"


class SourceFormat(StrEnum):
    sentinel2_l2a = "sentinel2_l2a"
    sentinel2_l1c = "sentinel2_l1c"
    landsat8 = "landsat8"
    drone_orthomosaic = "drone_orthomosaic"
    custom = "custom"


class JobStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class BandMapping(BaseModel):
    red: int | None = None
    green: int | None = None
    blue: int | None = None
    nir: int | None = None
    rededge: int | None = None  # red-edge (B5/B6/B7) — لـNDRE (النيتروجين)
    swir1: int | None = None
    swir2: int | None = None  # لمؤشّرات التربة (BSI/NDTI/SATVI)
    scl: int | None = None
    clp: int | None = None  # s2cloudless cloud probability (0..100 or 0..1), optional
    clm: int | None = None  # s2cloudless cloud mask: 1=cloud, 0=clear, optional


class ProcessRequest(BaseModel):
    tenant_id: str
    field_id: str | None = None
    raster_url: str | None = None
    indicator: IndicatorKind
    source_format: SourceFormat
    bands: BandMapping
    clip_polygon_geojson: dict | None = None
    apply_cloud_mask: bool = True
    # تحويل DN→انعكاس [0,1] للمؤشّرات المعتمِدة على المقياس (EVI/SAVI/MSAVI). افتراضيّاً
    # تُحترَم بيانات scale/offset المُعلَنة في الراستر؛ هذان يتجاوزانها يدويّاً لمصادر
    # تورّد DN خاماً دون إعلان (مثل بعض أصول Sentinel-2: reflectance_scale=0.0001).
    reflectance_scale: float | None = None
    reflectance_offset: float | None = None
    tiling_strategy: str = "pyramid"
    zoom_min: int = 10
    zoom_max: int = 18
    # provenance (#7): تثبيت المصدر لإعادة الإنتاج
    scene_id: str | None = None  # item_id من STAC search
    capture_datetime: str | None = None  # وقت التقاط القمر
    # مؤشّر محسوب مسبقاً (CDSE Process API): الراستر نطاق-واحد جاهز للمؤشّر — لا band math.
    precomputed_index: bool = False
    provider: str | None = None  # مصدر الصورة (مثل "cdse" / "element84") للأصل (provenance)
    # v143 (FINDING-004): مراجعة هندسة الحقل (field_geometry_history.revision) السارية
    # وقت إطلاق المعالجة — تُسجَّل على raster_assets للنَّسَب end-to-end. None ⇒ غير معروفة.
    geometry_revision: int | None = None


class BatchProcessRequest(BaseModel):
    """معالجة دفعيّة: عدّة مؤشّرات من نفس المشهد في مهمّة واحدة (كفاءة).

    بدل طلب لكلّ مؤشّر (يقرأ النطاقات مرّة لكلّ منها)، هذا يقرأ المشهد مرّة
    ويحسب كلّ المؤشّرات — توفير I/O كبير، مهمّ لقلب النظام تحت الحمل.
    """

    tenant_id: str
    field_id: str | None = None
    raster_url: str | None = None
    indicators: list[IndicatorKind]  # قائمة المؤشّرات (NDVI + NDRE + NDSI ...)
    source_format: SourceFormat
    bands: BandMapping
    clip_polygon_geojson: dict | None = None
    apply_cloud_mask: bool = True
    scene_id: str | None = None
    capture_datetime: str | None = None
    geometry_revision: int | None = None  # v143 (FINDING-004): نَسَب هندسة الحقل


class SearchRequest(BaseModel):
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    datetime_start: str
    datetime_end: str
    max_cloud_pct: float = 30
    limit: int = 20


class HistoricalBackfillPreset(StrEnum):
    """Preset windows for historical imagery backfill.

    last_2_years: default on field creation — two seasons of history for trend +
        season-over-season comparison (best-practice agronomic baseline window).
    auto_12_months: lighter one-season bootstrap (legacy default; kept for opt-in).
    extended_3_years: deeper season comparison and recurring weak-zone analysis.
    research_5_years: enterprise/research tier; heavier cost and storage.
    custom: explicit from_date/to_date or months.
    """

    last_2_years = "last_2_years"
    auto_12_months = "auto_12_months"
    extended_3_years = "extended_3_years"
    research_5_years = "research_5_years"
    custom = "custom"


_BACKFILL_PRESET_MONTHS = {
    HistoricalBackfillPreset.last_2_years: 24,
    HistoricalBackfillPreset.auto_12_months: 12,
    HistoricalBackfillPreset.extended_3_years: 36,
    HistoricalBackfillPreset.research_5_years: 60,
}


class HistoricalBackfillRequest(BaseModel):
    """Backfill historical satellite imagery for a field using current geometry.

    The request is intentionally configurable instead of hard-coded. This allows the
    platform to run a cheap automatic 12-month bootstrap on field creation, and let
    users opt into 3-year/5-year or custom history only when they need it.
    """

    tenant_id: str | None = None
    preset: HistoricalBackfillPreset = HistoricalBackfillPreset.last_2_years
    from_date: str | None = None
    to_date: str | None = None
    months: int | None = Field(default=None, ge=1, le=120)
    indices: list[IndicatorKind] = Field(
        default_factory=lambda: [
            IndicatorKind.ndvi,
            IndicatorKind.ndmi,
            IndicatorKind.savi,
            IndicatorKind.evi,
        ]
    )
    max_cloud_pct: float = Field(default=50, ge=0, le=100)
    limit_per_month: int = Field(default=8, ge=1, le=8)
    geometry_revision: int | None = None  # v144: نَسَب هندسة الحقل لتشغيلة backfill
    apply_cloud_mask: bool = True
    source: str = Field(default="sentinel-2")
    clip_polygon_geojson: dict | None = None
    dry_run: bool = False


class AutoBackfillPolicy(BaseModel):
    enabled: bool = True
    default_preset: HistoricalBackfillPreset = HistoricalBackfillPreset.last_2_years
    extended_preset: HistoricalBackfillPreset = HistoricalBackfillPreset.extended_3_years
    research_preset: HistoricalBackfillPreset = HistoricalBackfillPreset.research_5_years
    default_indices: list[str] = ["truecolor", "ndvi", "ndmi", "ndre", "msavi", "ndwi", "ndsi"]
    max_cloud_pct: float = 50
    note: str = (
        "Use last_2_years on field creation (two-season agronomic baseline). Core "
        "timeline imagery follows agronomic policy: Sentinel-2 scenes every 3-5 days "
        "when clear scene percentage is >=50% (cloud <=50%), with >=70% clear marked "
        "high quality. Advanced indicators remain opt-in/on-demand."
    )


class SceneCandidate(BaseModel):
    """A STAC/scene candidate normalized for quality ranking.

    Inspired by Sentinel Hub least-cloud mosaicking and common STAC quality filters:
    AOI cloud percentage is strongest, then recency, then field coverage and provider
    quality/confidence. All fields are optional so provider-specific payloads can be
    ranked without brittle adapters.
    """

    item_id: str | None = None
    datetime: str | None = None
    cloud_cover_pct: float | None = None
    aoi_cloud_pct: float | None = None
    coverage_pct: float | None = None
    view_angle: float | None = None
    provider_quality: float | None = None
    source: str | None = None
    properties: dict | None = None


class SceneRankRequest(BaseModel):
    scenes: list[SceneCandidate]
    mode: str = Field(default="best_available")
    max_cloud_pct: float = Field(default=40, ge=0, le=100)
    prefer_recent_days: int = Field(default=45, ge=1, le=3650)


class MosaicPlanRequest(BaseModel):
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    datetime_start: str
    datetime_end: str
    max_cloud_pct: float = Field(default=40, ge=0, le=100)
    limit: int = Field(default=20, ge=1, le=100)
    mosaic_rule: str = Field(default="least_cloud_then_recent")


class GeoParquetExportRequest(BaseModel):
    tenant_id: str | None = None
    field_ids: list[str] | None = None
    include_raster_assets: bool = True
    output_name: str = Field(default="field_analytics")


# ─── Scene ranking / historical backfill selection policy ─────────────
# Extracted from main.py; re-exported under legacy names so routers/tests/workers
# that import main._scene_* keep working without behavior drift.
import scene_policy  # noqa: E402

CORE_TIMELINE_INDICES = scene_policy.CORE_TIMELINE_INDICES
NDVI_PULL_MIN_CLEAR_PCT = scene_policy.NDVI_PULL_MIN_CLEAR_PCT
NDVI_PULL_MAX_CLOUD_PCT = scene_policy.NDVI_PULL_MAX_CLOUD_PCT
NDVI_HIGH_QUALITY_CLEAR_PCT = scene_policy.NDVI_HIGH_QUALITY_CLEAR_PCT
NDVI_PULL_MIN_SPACING_DAYS = scene_policy.NDVI_PULL_MIN_SPACING_DAYS
NDVI_PULL_TARGET_SPACING_DAYS = scene_policy.NDVI_PULL_TARGET_SPACING_DAYS

_scene_datetime = scene_policy.scene_datetime
_scene_to_dict = scene_policy.scene_to_dict
_scene_cloud_pct = scene_policy.scene_cloud_pct
_scene_clear_pct = scene_policy.scene_clear_pct
_scene_quality_label = scene_policy.scene_quality_label
_scene_day_key = scene_policy.scene_day_key
_select_backfill_scenes_by_policy = scene_policy.select_backfill_scenes_by_policy
_scene_quality_score = scene_policy.scene_quality_score
_rank_scenes = scene_policy.rank_scenes


# صيانة كاش البلاطات (تعقيم المسار + الإبطال + الإخلاء) في وحدة مستقلّة بلا FastAPI
# كي يستوردها عامل الإبطال بخفّة وتُختبَر بمعزل. نُعيد تصديرها هنا للتوافق.
import tile_cache_io  # noqa: E402
import tile_cache_maint  # noqa: E402

invalidate_field_tile_cache = tile_cache_maint.invalidate_field_tile_cache
prune_tile_cache = tile_cache_maint.prune_tile_cache
_safe_cache_segment = tile_cache_maint.safe_cache_segment
_tile_cache_field_dir = tile_cache_maint.tile_cache_field_dir


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
        UPLOAD_DIR, _safe_cache_segment, field_id, index, date, z, x, y, tenant_id, v
    )


def _read_tile_cache(path: str) -> bytes | None:
    return tile_cache_io.read_tile_cache(path, enabled=_tile_cache_enabled())


def _write_tile_cache(path: str, data: bytes) -> None:
    try:
        tile_cache_io.write_tile_cache(path, data, enabled=_tile_cache_enabled())
    except OSError as e:
        logger.warning("tile cache write skipped: %s", type(e).__name__)


# P2 observability: tile/tilejson counters kept in-process so Prometheus can
# explain map failures without reading nginx logs. Labels are intentionally
# low-cardinality where possible; field_id is exposed only in the diagnostic
# JSON endpoint, not Prometheus.
_TILE_OBS = {
    "tilejson_requests_total": 0,
    "tilejson_available_total": 0,
    "tilejson_unavailable_total": 0,
    "tile_requests_total": 0,
    "tile_cache_hits_total": 0,
    "tile_cache_misses_total": 0,
    "tile_transparent_total": 0,
    "tile_render_errors_total": 0,
}
_TILE_OBS_BY_INDEX: dict[str, dict[str, int]] = {}


def _obs_inc(name: str, index: str | None = None, amount: int = 1) -> None:
    _TILE_OBS[name] = int(_TILE_OBS.get(name, 0)) + amount
    if index:
        bucket = _TILE_OBS_BY_INDEX.setdefault(index, {})
        bucket[name] = int(bucket.get(name, 0)) + amount


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


# ─── حالة المهامّ: Redis (مشترك + يبقى بعد إعادة التشغيل) مع ارتداد للذاكرة ──
# كانت _jobs مجرّد dict في الذاكرة ⇒ تُفقد عند إعادة التشغيل ولا تُشارَك عبر
# العمّال (فيفشل /jobs/{id}/result على عامل آخر). JobStore يخزّن في Redis إن
# توفّر REDIS_URL وكان قابلاً للوصول، وإلّا يرتدّ للذاكرة (تطوير/CI بلا Redis).
# يستخدم عميل redis متزامن (sync) لتجنّب كسر حلقة الحدث: الكتابة تجري في خيط
# الخلفيّة (threadpool) والقراءة في حلقة الخادم — انظر job_store.py.
_jobs = JobStore(redis_url=os.getenv("REDIS_URL"))
_layers: dict[str, dict] = {}
# فهرس حقل→قائمة معرّفات الطبقات (لإيجاد أحدث COG لحقل في شبكة المؤشّر)
_field_layers: dict[str, list[str]] = {}

# v11-F3/F5: إخلاء طبقات الذاكرة عبر العمليّات — عامل الإبطال (عمليّة منفصلة) يعلّم DB
# stale ويحذف بلاطات القرص، لكنّه لا يصل ذاكرة raster-service؛ فتبقى _layers القديمة
# (هندسة قديمة) تُخدَّم حتّى إعادة الترطيب. الحلّ: العامل ينشر field_id على قناة Redis،
# وهذه الخدمة تشترك فيها وتُخلي طبقات الحقل فوراً. best-effort + راية + تدهور لطيف.
_LAYER_EVICT_CHANNEL = os.getenv("RASTER_LAYER_EVICT_CHANNEL", "raster:layer_evict")


def _layer_evict_enabled() -> bool:
    return str(os.getenv("RASTER_LAYER_EVICT_ENABLED", "true")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _evict_field_layers(field_id: str) -> int:
    """يُزيل كلّ طبقات الحقل من الذاكرة (_layers/_field_layers). يُرجِع العدد المُزال.

    يُستدعى عند إبطال حدود الحقل (رسالة Redis من عامل الإبطال) كي لا تُخدَّم طبقة
    مقصوصة على هندسة قديمة بعد التعديل. آمن — لا يرمي، وغياب الحقل ⇒ 0."""
    if not field_id:
        return 0
    lids = _field_layers.pop(field_id, [])
    for lid in lids:
        _layers.pop(lid, None)
    if lids:
        logger.info(
            "evicted %d in-memory layer(s) for field %s (cache invalidation)", len(lids), field_id
        )
    return len(lids)


async def _layer_evict_subscriber() -> None:
    """يشترك في قناة Redis لإخلاء طبقات الحقل عند إبطال الحدود (v11-F3/F5).

    مرن: يُعيد الاتّصال عند انقطاع Redis، ولا يُسقِط الخدمة إن غاب Redis/العميل."""
    import asyncio as _asyncio

    url = os.getenv("REDIS_URL")
    if not url:
        logger.info("layer-evict subscriber معطَّل (لا REDIS_URL)")
        return
    try:
        import redis.asyncio as _aioredis
    except ImportError:
        logger.info("layer-evict subscriber معطَّل (حزمة redis.asyncio غائبة)")
        return
    while True:
        try:
            client = _aioredis.from_url(url, encoding="utf-8", decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe(_LAYER_EVICT_CHANNEL)
            logger.info("layer-evict subscriber مشترِك في %s", _LAYER_EVICT_CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                _evict_field_layers(str(message.get("data") or "").strip())
        except _asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — انقطاع Redis لا يُسقِط الخدمة
            logger.warning("layer-evict subscriber انقطع (إعادة محاولة خلال 5s): %s", e)
            await _asyncio.sleep(5)


# ─── بحث الصور عبر STAC/CDSE ──────────────────────────────────────
import stac_search as stac_search_helpers  # noqa: E402

stac_search_helpers.configure(
    stac=_stac,
    logger=logger,
    earth_search_url=EARTH_SEARCH_URL,
    http_timeout=HTTP_TIMEOUT,
    historical_search_provider=HISTORICAL_SEARCH_PROVIDER,
    sentinel_collection=SENTINEL_COLLECTION,
    sentinel1_collection=SENTINEL1_COLLECTION,
    landsat_collection=LANDSAT_COLLECTION,
    dem_collection=DEM_COLLECTION,
    landsat_unique_indices=LANDSAT_UNIQUE_INDICES,
    landsat_direct_raster_indices=LANDSAT_DIRECT_RASTER_INDICES,
    landsat_derived_indices=LANDSAT_DERIVED_INDICES,
    landsat_duplicate_sentinel_indices=LANDSAT_DUPLICATE_SENTINEL_INDICES,
    landsat_thermal_asset_candidates=LANDSAT_THERMAL_ASSET_CANDIDATES,
)

# Compatibility façade: routers/tests still import these helpers from main.py.
_band_urls_from_assets = stac_search_helpers.band_urls_from_assets
_stac_query = stac_search_helpers.stac_query
_stac_search = stac_search_helpers.stac_search
_stac_search_cdse = stac_search_helpers.stac_search_cdse
_stac_search_element84 = stac_search_helpers.stac_search_element84
_stac_search_radar = stac_search_helpers.stac_search_radar
_landsat_thermal_href = stac_search_helpers.landsat_thermal_href
_landsat_unique_payload = stac_search_helpers.landsat_unique_payload
_stac_search_landsat = stac_search_helpers.stac_search_landsat
_stac_search_landsat_unique = stac_search_helpers.stac_search_landsat_unique
_stac_search_dem = stac_search_helpers.stac_search_dem


def _process_backfill_scene_cdse(
    scene: dict,
    index: str,
    field_id: str,
    tenant_id: str | None,
    clip: dict | None,
    geometry_revision,
    jid: str,
) -> None:
    """يعالج مشهداً مُكتشَفاً من كتالوج CDSE لمؤشّر واحد عبر Process API.

    مسار المعالجة التاريخيّة على CDSE (بلا نطاقات COG من Element84): يُثبِّت نافذة
    زمنيّة على يوم المشهد، يطلب المؤشّر خادميّاً (evalscript، مقصوصاً على ``clip``)،
    يكتب TIFF، ثمّ يُشغّل ``_run_processing`` كأصل precomputed (provider="cdse").
    متزامن (httpx + _run_processing) — يُستدعى عبر threadpool من مسار backfill.
    """
    import cdse_client

    dt = scene.get("datetime") or ""
    day = dt[:10]
    if len(day) != 10:
        raise RuntimeError("CDSE scene بلا تاريخ صالح")
    bbox = scene.get("bbox") or _bbox_from_geojson(clip)
    if not bbox:
        raise RuntimeError("bbox مطلوب لمعالجة مشهد CDSE")
    tiff = cdse_client.get_client().process_index(
        index=index,
        bbox=bbox,
        time_from=f"{day}T00:00:00Z",
        time_to=f"{day}T23:59:59Z",
        geometry=clip,
        max_cloud_pct=40.0,
    )
    if not tiff:
        raise RuntimeError("CDSE process_index أرجع استجابة فارغة")
    tif_path = os.path.join(UPLOAD_DIR, f"cdse_bf_{index}_{uuid.uuid4().hex[:8]}.tif")
    with open(tif_path, "wb") as fh:
        fh.write(tiff)
    preq = ProcessRequest(
        tenant_id=tenant_id or "",
        field_id=field_id,
        raster_url=tif_path,
        indicator=IndicatorKind(index),
        source_format=SourceFormat.sentinel2_l2a,
        bands=BandMapping(),
        precomputed_index=True,
        provider="cdse",
        scene_id=scene.get("item_id"),
        capture_datetime=dt,
        clip_polygon_geojson=clip,
        apply_cloud_mask=False,  # CDSE قنّع الغيوم خادميّاً (maxCloudCoverage + SCL)
        geometry_revision=geometry_revision,
    )
    _run_processing(jid, preq)


# ─── lifespan + التطبيق ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("raster-service starting (Element84 Earth Search)")
    # اضبط GDAL لـ/vsis3 عند ضبط S3 (no-op إن لم يُضبط) — تخزين COG قابل للتوسّع.
    object_store.gdal_configure()
    # FINDING-001: ارفض الإقلاع إن تجاوز دور الاتّصال RLS (fail-closed افتراضيّاً).
    # raster يكتب أصول NDVI لكلّ مستأجِر (db_persist، اتّصال per-call).
    import os as _os

    from shared.db_role_guard import assert_dsn_role_rls_safe

    await assert_dsn_role_rls_safe(_os.getenv("DATABASE_URL", ""), service="raster-service")
    # v11-F3/F5: مشترِك إخلاء طبقات الذاكرة (best-effort، لا يُسقِط الإقلاع إن غاب Redis).
    import asyncio as _asyncio
    import contextlib as _contextlib

    _evict_task = None
    if _layer_evict_enabled():
        _evict_task = _asyncio.create_task(_layer_evict_subscriber())
    yield
    if _evict_task is not None:
        _evict_task.cancel()
        with _contextlib.suppress(_asyncio.CancelledError):
            await _evict_task
    logger.info("raster-service stopping")


app = FastAPI(title="SAHOOL Raster Service", version="9.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-Id"],
    allow_credentials=True,
)


# ─── سياق المستأجِر للطلب (إصلاح ترطيب raster_assets عبر RLS) ──────
# مسار قراءة الراستر كان بلا هويّة مستأجِر ⇒ db_persist.fetch_latest_asset(tenant_id=None)
# يفشل دائماً (RLS في v14 + الفلتر الصريح يحتاجان app.current_tenant). نلتقط الترويسة
# الموثوقة X-Tenant-Id (يحقنها البوّابة بعد التحقّق من JWT؛ proxy_params يُفرغ أيّ ترويسة
# منتحَلة من العميل) ونمرّرها لطبقة القاعدة عند إعادة الترطيب. غيابها ⇒ None ⇒ سلوك
# fail-closed الحالي (لا انحدار: RLS يحجب بلا مستأجِر).
_REQ_TENANT: ContextVar[str | None] = ContextVar("req_tenant", default=None)

try:
    from shared.security.tenant_context import resolve_tenant_context as _resolve_tenant_context
except ImportError:  # pragma: no cover - service can still run from its folder in minimal CI

    def _resolve_tenant_context(
        request, tid: str | None = None, tenant_id: str | None = None
    ) -> str | None:
        def _clean(value: str | None) -> str | None:
            if not value:
                return None
            return value.strip() or None

        return _clean(request.headers.get("X-Tenant-Id")) or _clean(tid) or _clean(tenant_id)


def _tenant_from_header(value: str | None) -> str | None:
    """Backwards-compatible normalizer used by tests and older call sites."""
    if not value:
        return None
    value = value.strip()
    return value or None


def _tenant_from_request(request) -> str | None:
    """يستخرج سياق المستأجر من الطلب.

    المسار الطبيعي الآمن هو `X-Tenant-Id` الذي تحقنه البوابة بعد JWT. لكن
    بلاطات الخريطة تُحمَّل كصور `<img>`/TileLayer ولا تستطيع دائماً إرسال
    ترويسات Authorization/axios. لذلك تقبل مسارات البلاطات أيضاً `tid` كـ
    tenant hint حتى يعمل التطوير المحلي وإعادة ترطيب `raster_assets` عبر RLS.

    لا يُستخدم `tid` وحده كإذن نهائي: `_require_field_tenant` يقارن tenant
    الطلب مع مالك الحقل من جدول `fields` عند توفر قاعدة البيانات، و
    `fetch_latest_asset` يضيف فلتر tenant_id صريحاً فوق RLS.
    """
    return _resolve_tenant_context(
        request,
        tid=request.query_params.get("tid"),
        tenant_id=request.query_params.get("tenant_id"),
    )


@app.middleware("http")
async def _tenant_context_mw(request, call_next):
    """يضبط سياق المستأجِر لكلّ طلب ويُعيده بعد الطلب."""
    token = _REQ_TENANT.set(_tenant_from_request(request))
    try:
        return await call_next(request)
    finally:
        _REQ_TENANT.reset(token)


# تفويض الحقل: ذاكرة TTL لمالك الحقل (tenant_id) تجنّباً لاستعلام قاعدة لكلّ بلاطة
# (البلاطات عالية التردّد). الملكيّة ثابتة (لا تتغيّر) ⇒ تخزين قصير آمن. القيمة None
# تعني «غير محسوم» (لم يُوجَد/قاعدة متعذّرة) وتُخزَّن مدّةً أقصر لتقليل الحِمل على
# مسار الهجوم دون تثبيت سلبيّ طويل.
_field_owner_cache: dict[str, tuple[str | None, float]] = {}
_FIELD_OWNER_TTL_OK = 300.0  # مالك معروف: ثابت ⇒ 5 دقائق
_FIELD_OWNER_TTL_MISS = 15.0  # غير محسوم: إعادة الفحص أسرع


async def _field_owner(field_id: str) -> str | None:
    """مالك الحقل من المصدر الموثوق (جدول fields عبر دالّة SECURITY DEFINER)، مع
    ذاكرة TTL. None ⇒ غير محسوم (بلا قاعدة/الحقل غير موجود). يرفع
    OwnerLookupUnavailable إن كانت القاعدة مُهيّأة لكن تعذّر الإثبات (يُترَك للمنادي
    ليُقرّر fail-closed). لا نُخبّئ حالة التعذّر."""
    import time as _t

    now = _t.monotonic()
    hit = _field_owner_cache.get(field_id)
    if hit is not None and hit[1] > now:
        return hit[0]
    import db_persist

    # OwnerLookupUnavailable يُمرَّر (لا يُلتقَط ولا يُخبّأ) ⇒ يقرّر _require_field_tenant
    # الحجب 503. None هنا = بلا قاعدة (DB-less مقصود) أو الحقل غير موجود ⇒ لا حجب.
    owner = await db_persist.field_owner_tenant(field_id)
    ttl = _FIELD_OWNER_TTL_OK if owner else _FIELD_OWNER_TTL_MISS
    _field_owner_cache[field_id] = (owner, now + ttl)
    return owner


async def _require_field_tenant(field_id: str, *, hide_existence: bool = False) -> None:
    """تفويض ملكيّة الحقل.

    جدول fields هو مصدر الحقيقة. كان الفحص يبدأ بكاش `_field_layers`؛ فإذا بقيت
    طبقات قديمة مرتبطة بمستأجر خاطئ كانت تسبق DB وتعيد 403 رغم أن الحقل نفسه
    يخصّ مستأجر الطلب. الآن نقرأ DB أولاً عندما تكون متاحة، ونستخدم الكاش فقط
    كدفاع عمق عند غياب مالك موثوق من DB/وضع DB-less.
    """
    req_tenant = _REQ_TENANT.get()
    import db_persist

    try:
        owner = await _field_owner(field_id)
    except db_persist.OwnerLookupUnavailable as e:
        raise HTTPException(503, "تعذّر إثبات ملكيّة الحقل — أعد المحاولة لاحقاً") from e

    if owner:
        if not req_tenant or owner != req_tenant:
            raise HTTPException(
                404 if hide_existence else 403,
                "الحقل غير موجود" if hide_existence else "الحقل لا يخصّ مستأجِرك",
            )
        # DB أثبت ملكية الحقل للطلب؛ لا تجعل طبقات ذاكرة قديمة/ملوثة تسمّم الطلب.
        # ننظف الفهرس من أي layer تحمل tenant_id مختلفاً حتى لا تعود 403 لاحقاً.
        kept: list[str] = []
        for lid in _field_layers.get(field_id, []):
            lyr = _layers.get(lid)
            cached_owner = lyr.get("tenant_id") if lyr else None
            if cached_owner and cached_owner != req_tenant:
                logger.warning(
                    "pruning stale field layer tenant cache field=%s layer=%s cached=%s request=%s",
                    field_id,
                    lid,
                    cached_owner,
                    req_tenant,
                )
                continue
            kept.append(lid)
        if kept != _field_layers.get(field_id, []):
            _field_layers[field_id] = kept
        return

    # DB-less/field not known: fall back to in-memory defense only.
    for lid in _field_layers.get(field_id, []):
        lyr = _layers.get(lid)
        cached_owner = lyr.get("tenant_id") if lyr else None
        if cached_owner and cached_owner != req_tenant:
            raise HTTPException(
                404 if hide_existence else 403,
                "الحقل غير موجود" if hide_existence else "الحقل لا يخصّ مستأجِرك",
            )


def _require_layer_tenant(layer_id: str) -> None:
    """تفويض سريع من الذاكرة لملكية الطبقة."""
    req_tenant = _REQ_TENANT.get()
    lyr = _layers.get(layer_id)
    owner = lyr.get("tenant_id") if lyr else None
    if owner and owner != req_tenant:
        raise HTTPException(403, "الطبقة لا تخصّ مستأجِرك")


async def _require_layer_tenant_authorized(layer_id: str) -> None:
    """تفويض ملكيّة الطبقة مع جعل DB مصدر الحقيقة عند توفره.

    الكاش قد يحتوي طبقة قديمة بمستأجر خاطئ بعد تبديل/إعادة ترطيب البيانات؛ لذلك
    نحاول حسم الملكية من `raster_assets` أولاً. إن أثبت DB المالك نثق به وننظف
    الكاش، وإن لم يعرف الطبقة نرجع لدفاع الذاكرة.
    """
    req_tenant = _REQ_TENANT.get()
    try:
        import db_persist

        db_owner = await db_persist.layer_owner_tenant(layer_id)
    except db_persist.OwnerLookupUnavailable as e:
        raise HTTPException(503, "تعذّر إثبات ملكيّة الطبقة — أعد المحاولة لاحقاً") from e

    if db_owner:
        if not req_tenant:
            raise HTTPException(403, "مستأجر الطلب مطلوب لقراءة الطبقة")
        if db_owner != req_tenant:
            raise HTTPException(403, "الطبقة لا تخصّ مستأجِرك")
        lyr = _layers.get(layer_id)
        if lyr and lyr.get("tenant_id") and lyr.get("tenant_id") != req_tenant:
            logger.warning(
                "correcting stale layer tenant cache layer=%s cached=%s db=%s",
                layer_id,
                lyr.get("tenant_id"),
                db_owner,
            )
            lyr["tenant_id"] = db_owner
        return

    # DB لا يعرف الطبقة: fallback لذاكرة العملية فقط.
    _require_layer_tenant(layer_id)
    lyr = _layers.get(layer_id)
    owner = lyr.get("tenant_id") if lyr else None
    if owner and not req_tenant:
        raise HTTPException(403, "مستأجر الطلب مطلوب لقراءة الطبقة")
    if not owner and not req_tenant:
        raise HTTPException(403, "مستأجر الطلب مطلوب لقراءة الطبقة")


def _public_cog_url(cog_url: str | None) -> str | None:
    """يُعيد cog_url فقط إن كان رابطاً عامّاً http(s) — وإلّا None.

    منع تسريب مسارات التخزين الداخليّة (file:// ، s3:// ، مضيف داخليّ) في استجابة
    tilejson المكشوفة للعميل (titiler_tiles). البلاطات الذاتيّة تعمل دون كشف المصدر."""
    if not cog_url:
        return None
    low = cog_url.strip().lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        return None  # file://, s3://, مسار داخليّ ⇒ لا يُكشَف
    # استبعاد المضيفات الداخليّة الشائعة (compose/k8s) — لا تُكشَف للعميل.
    if any(h in low for h in ("sahool-", "minio", "localhost", "127.0.0.1", ":9000", ".internal")):
        return None
    return cog_url


# ─── مسارات بحث الصور (public_catalog: بحث صور أقمار عامّة بـbbox — لا بيانات مستأجِر) ──


class TimeSeriesAnalyzeRequest(BaseModel):
    scene_values: list[dict]  # [{"datetime": "...", "mean": 0.5}, ...]


class ManagementZonesRequest(BaseModel):
    pixel_values: list[float]
    n_zones: int = 3
    base_rate: float | None = None
    strategy: str = "compensate"


# حدّ أعلى لحجم شبكة التغيير (256×256). يمنع استهلاك ذاكرة/CPU كبير (DoS) من
# طلب واحد قبل تحويل numpy. شبكات الموبايل أصغر بكثير عمليّاً.
MAX_CHANGE_GRID_CELLS = 256 * 256


class ChangeDetectRequest(BaseModel):
    field_id: str
    index: str = "ndvi"
    date_before: str
    date_after: str
    grid_before: list[list[float | None]]  # شبكة المؤشّر للتاريخ الأقدم
    grid_after: list[list[float | None]]  # شبكة المؤشّر للتاريخ الأحدث
    slight_threshold: float = 0.1
    severe_threshold: float = 0.2


class FvcComputeRequest(BaseModel):
    field_id: str
    date: str
    ndvi_grid: list[list[float | None]]  # شبكة NDVI مُحسبة من COG
    method: str = "cumulative_frequency"  # | global_constant | dynamic_range
    ndvi_soil: float | None = None  # لـdynamic_range فقط
    ndvi_veg: float | None = None


class SarRviRequest(BaseModel):
    field_id: str
    date: str
    vv_grid: list[list[float | None]]  # σ°_VV (قدرة خطّيّة أو dB)
    vh_grid: list[list[float | None]]  # σ°_VH
    in_db: bool = False  # هل القيم بالديسيبل؟ (تُحوَّل للخطّي قبل النسبة)


class TerrainRequest(BaseModel):
    dem_url: str
    pixel_size_m: float = 30.0


# ─── الفحوص ───────────────────────────────────────────────────────


# ─── معالجة الراستر: الرفع ────────────────────────────────────────
UPLOAD_DIR = os.getenv("RASTER_UPLOAD_DIR", "/tmp/sahool_rasters")

_SSRF_BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal", "metadata"}


def _safe_raster_source(url: str | None) -> str:
    """يتحقّق من مصدر راستر آمن قبل rasterio.open — يمنع path traversal وSSRF.

    file:// أو مسار محلّيّ مطلق: يُسمَح **فقط** تحت UPLOAD_DIR (realpath، لا
    ../traversal) ⇒ يمنع قراءة ملفّات عشوائيّة (file:///etc/passwd). قبول المسار
    المطلق ضروريّ لأنّ خطوط الأنابيب الداخليّة (backfill/process-from-stac/CDSE)
    تمرّر مخرجاتها (VRT/GeoTIFF تحت UPLOAD_DIR) كمسار خام — رفضُه أسقط كلّ مهامّ
    backfill بـHTTPException 400 «مخطّط URL غير مدعوم» (بلاغ 2026-07-04)؛ الاحتواء
    تحت UPLOAD_DIR هو نفسه للمسارَين فلا اتّساع أمنيّاً. http(s): يُسمَح
    (STAC/object-store) مع حجب عنوان metadata السحابي. أيّ غير ذلك ⇒ 400.
    (مراجعة الجولة ٣ — أمن.)
    """
    if not url or not isinstance(url, str):
        raise HTTPException(400, "مصدر راستر غير صالح")
    if url.startswith("file://") or url.startswith("/"):
        raw = url[len("file://") :] if url.startswith("file://") else url
        path = os.path.realpath(raw)
        base = os.path.realpath(UPLOAD_DIR)
        if path != base and not path.startswith(base + os.sep):
            raise HTTPException(400, "مسار ملفّ خارج المجلّد المسموح (traversal مرفوض)")
        return path
    if url.startswith(("http://", "https://")):
        host = (urlparse(url).hostname or "").lower()
        if host in _SSRF_BLOCKED_HOSTS:
            raise HTTPException(400, "مضيف محجوب (SSRF)")
        return url
    raise HTTPException(400, "مخطّط URL غير مدعوم لمصدر الراستر")


# مصادقة خدمة-لخدمة: رفع الراستر يكتب ملفّات — منع إساءة التخزين/الحقن
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")


def _require_service_token(x_agent_token: str = Header(None)) -> None:
    if not AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — الرفع معطّل بأمان")
    if not hmac.compare_digest(x_agent_token or "", AGENT_TOKEN):
        raise HTTPException(401, "توكن خدمة غير صالح")


os.makedirs(UPLOAD_DIR, exist_ok=True)


# ─── المعالجة غير المتزامنة (job) ─────────────────────────────────
# صيغ المؤشّرات (للتوثيق + التنفيذ عند توفّر rasterio)
_INDICATOR_FORMULAS = {
    "ndvi": "(NIR - RED) / (NIR + RED)",
    "evi": "2.5 * (NIR - RED) / (NIR + 6*RED - 7.5*BLUE + 1)",
    "savi": "1.5 * (NIR - RED) / (NIR + RED + 0.5)",
    "ndwi": "(GREEN - NIR) / (GREEN + NIR)",
    "ndmi": "(NIR - SWIR1) / (NIR + SWIR1)",
    "gndvi": "(NIR - GREEN) / (NIR + GREEN)",
    "ndre": "(NIR - REDEDGE) / (NIR + REDEDGE)  # النيتروجين/الكلوروفيل (red-edge)",
    "reci": "(NIR / REDEDGE) - 1  # Red-edge chlorophyll index",
    "gci": "(NIR / GREEN) - 1  # Green chlorophyll index",
    "arvi": "(NIR - (2*RED - BLUE)) / (NIR + (2*RED - BLUE))",
    "sipi": "(NIR - BLUE) / (NIR - RED)",
    "nbr": "(NIR - SWIR2) / (NIR + SWIR2)",
    "ccci": "NDRE / NDVI  # Canopy chlorophyll content index",
    "msi": "SWIR1 / NIR  # Moisture Stress Index (الإجهاد المائي)",
    "msavi": "(2*NIR + 1 - sqrt((2*NIR+1)^2 - 8*(NIR-RED))) / 2  # Modified SAVI (L ذاتي)",
    "moisture": "(NIR - SWIR1) / (NIR + SWIR1)  # NDMI رطوبة المحتوى (للواجهة)",
    "fapar": "أساسها NDVI (علاقة تجريبيّة)",
    "vari": "(GREEN - RED) / (GREEN + RED - BLUE)",  # RGB-only للدرون
    "gli": "(2*GREEN - RED - BLUE) / (2*GREEN + RED + BLUE)",
    "tgi": "GREEN - 0.39*RED - 0.61*BLUE",
    # مؤشّرات التربة (من soil_indices.py — انظر SOIL_INDICES_RESEARCH)
    "bsi": "((SWIR2+RED)-(NIR+BLUE)) / ((SWIR2+RED)+(NIR+BLUE))",
    "bi": "sqrt((RED^2+GREEN^2)/2)",
    "bi2": "sqrt((RED^2+GREEN^2+NIR^2)/3)",
    "ndti": "(SWIR1-SWIR2)/(SWIR1+SWIR2)",
    "dbsi": "((SWIR1-GREEN)/(SWIR1+GREEN)) - NDVI",
    "ndsi": "(SWIR1-SWIR2)/(SWIR1+SWIR2)  # salinity — حرج لليمن",
    "satvi": "((SWIR1-RED)/(SWIR1+RED+L))*(1+L) - SWIR2/2",
}


def _quality_from_cloud_pct(cloud_pct: float | None, *, masked: bool = True) -> dict:
    """Return a conservative 0..1 quality/confidence score for a raster layer/pixel.

    cloud_pct is computed over the clipped field AOI when SCL is available. Scene-level
    cloud cover is intentionally treated as weaker evidence elsewhere.
    """
    if cloud_pct is None:
        return {
            "confidence": 0.55,
            "quality": "unknown",
            "reason": "cloud_quality_unavailable",
        }
    cp = max(0.0, min(100.0, float(cloud_pct)))
    score = max(0.0, min(1.0, 1.0 - (cp / 100.0)))
    if not masked:
        score = min(score, 0.65)
    if cp <= 5:
        label = "high"
    elif cp <= 20:
        label = "medium"
    elif cp <= 50:
        label = "low"
    else:
        label = "very_low"
    return {
        "confidence": round(score, 3),
        "quality": label,
        "cloud_pct": round(cp, 3),
        "reason": "field_aoi_scl_cloud_pct",
    }


def _pixel_quality(layer: dict, value: float | None) -> dict:
    """Quality metadata for a single sampled indicator pixel.

    The COG contains the already masked indicator. If the sampled value is valid, the
    best available quality signal is the layer-level AOI cloud percentage from SCL.
    """
    if value is None:
        return {"confidence": 0.0, "quality": "nodata", "reason": "nodata_or_cloud_masked"}
    q = _quality_from_cloud_pct(
        layer.get("cloud_pct"), masked=bool(layer.get("cloud_mask_applied", True))
    )
    if q["quality"] == "unknown" and layer.get("provider") in ("cdse", "sentinelhub", "element84"):
        q["reason"] = "provider_known_but_pixel_qa_unavailable"
    return q


# Persistence helpers are implemented outside main.py; keep private aliases here
# for existing tests and routers that still import from main during the staged split.
# NB: the phase-4 extraction left raster_asset_persistence unwired — main lost
# _persist_raster_asset/_is_valid_field_id_text while raster_job_orchestration still
# calls ctx._persist_raster_asset (AttributeError on every persist) and tests import
# main._is_valid_field_id_text. Re-bind them here (form required by the decomposition gate).
from raster_asset_persistence import (  # noqa: E402, I001
    _is_valid_field_id_text as _is_valid_field_id_text,
    _is_valid_uuid_text as _is_valid_uuid_text,
    persist_raster_asset as _persist_raster_asset,  # noqa: F401
)

import raster_job_orchestration  # noqa: E402


def _run_processing(job_id: str, req: ProcessRequest):
    """Compatibility wrapper for staged raster main.py decomposition."""
    return raster_job_orchestration.run_processing(sys.modules[__name__], job_id, req)


def _run_batch_processing(job_id: str, req: BatchProcessRequest):
    """Compatibility wrapper for staged raster main.py decomposition."""
    return raster_job_orchestration.run_batch_processing(sys.modules[__name__], job_id, req)


def _process_precomputed_pixels(req: ProcessRequest, layer_id: str):
    """مسار CDSE: المؤشّر محسوب خادميّاً (evalscript) فالراستر نطاق-واحد جاهز.

    يقرأ النطاق الأوّل مباشرةً (لا band math، لا تحويل انعكاس)، يعيد إسقاط الحدود إلى
    EPSG:4326، يحسب الإحصاءات، ويكتب COG محسّناً (نفس مسار التخزين/الأصل). يُرجِع
    ``(stats, bounds_4326, resolution_m, meta)`` بنفس تعاقُد :func:`_process_pixels`.
    صدق: لا قناع SCL (CDSE يقنّع الغيوم بـdataMask/maxCloudCoverage خادميّاً)؛ ``NaN`` = لا بيانات.
    """
    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds

    # الصورة الخام (truecolor) راستر RGBA متعدّد النطاقات — مسار حفظ منفصل (لا إحصاء
    # مؤشّر/نطاق واحد؛ لا يمرّ عبر _INDICATOR_FORMULAS). يقرأ 4 نطاقات ويكتب COG RGBA.
    if req.indicator.value == "truecolor":
        return _process_precomputed_truecolor(req)

    with rasterio.open(_safe_raster_source(req.raster_url)) as src:
        res_m = abs(src.res[0])
        src_crs = src.crs
        if src_crs is not None:
            bounds = list(transform_bounds(src_crs, "EPSG:4326", *src.bounds))
        else:
            bounds = list(src.bounds)
        arr = src.read(1).astype("float32")
        if src.nodata is not None:
            arr = np.where(arr == src.nodata, np.nan, arr)
        transform = src.transform

    valid = np.isfinite(arr)
    vals = arr[valid]
    stats = {
        "min": float(np.min(vals)) if vals.size else 0.0,
        "max": float(np.max(vals)) if vals.size else 0.0,
        "mean": float(np.mean(vals)) if vals.size else 0.0,
        "std": float(np.std(vals)) if vals.size else 0.0,
        "valid_pixels": int(valid.sum()),
        "nodata_pixels": int((~valid).sum()),
    }
    cog_url = None
    cog_crs = str(src_crs or "EPSG:4326")
    try:
        import cog_writer

        cog_uid = uuid.uuid4().hex[:8]
        cog_path = os.path.join(UPLOAD_DIR, f"{req.indicator.value}_{cog_uid}.tif")
        cog_info = cog_writer.write_cog(arr, cog_path, transform, crs=cog_crs, nodata=RASTER_NODATA)
        stats["cog"] = cog_info
        if cog_info.get("written"):
            cog_url = object_store.upload_cog(
                cog_path, f"{req.field_id or 'nofield'}/{req.indicator.value}_{cog_uid}.tif"
            )
    except Exception as _e:  # noqa: BLE001 — حفظ COG اختياري لا يُفشل الحساب
        stats["cog"] = {"written": False, "reason": str(_e)}
    meta = {
        "cog_url": cog_url,
        "cog_crs": cog_crs,
        "srid": (src_crs.to_epsg() if src_crs is not None else 4326),
        "nodata": RASTER_NODATA,
    }
    return stats, bounds, res_m, meta


def _process_precomputed_truecolor(req: ProcessRequest):
    """مسار CDSE للصورة الخام (truecolor): الراستر RGBA (4 نطاقات UINT8) جاهز خادميّاً.

    يقرأ النطاقات كلّها، يحسب إحصاء توفّر بسيطاً من قناة ألفا (لا min/max/mean لمؤشّر —
    RGB بلا معنًى إحصائيّ)، ويكتب COG RGBA محسّناً (``write_rgba_cog``) ثمّ يرفعه. يُرجِع
    ``(stats, bounds_4326, resolution_m, meta)`` بنفس تعاقُد :func:`_process_precomputed_pixels`."""
    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(_safe_raster_source(req.raster_url)) as src:
        res_m = abs(src.res[0])
        src_crs = src.crs
        if src_crs is not None:
            bounds = list(transform_bounds(src_crs, "EPSG:4326", *src.bounds))
        else:
            bounds = list(src.bounds)
        arr = src.read()  # (bands, H, W) uint8
        transform = src.transform

    # صدق الإحصاء: البكسل «صالح» = ألفا>0 (النطاق الرابع) إن وُجد، وإلّا كلّه صالح.
    if arr.shape[0] >= 4:
        valid = arr[3] > 0
    else:
        valid = np.ones(arr.shape[1:], dtype=bool)
    stats = {
        "min": 0.0,
        "max": 255.0,
        "mean": 0.0,
        "std": 0.0,
        "valid_pixels": int(valid.sum()),
        "nodata_pixels": int((~valid).sum()),
    }
    cog_url = None
    cog_crs = str(src_crs or "EPSG:4326")
    try:
        import cog_writer

        cog_uid = uuid.uuid4().hex[:8]
        cog_path = os.path.join(UPLOAD_DIR, f"truecolor_{cog_uid}.tif")
        cog_info = cog_writer.write_rgba_cog(arr, cog_path, transform, crs=cog_crs)
        stats["cog"] = cog_info
        if cog_info.get("written"):
            cog_url = object_store.upload_cog(
                cog_path, f"{req.field_id or 'nofield'}/truecolor_{cog_uid}.tif"
            )
    except Exception as _e:  # noqa: BLE001 — حفظ COG اختياري لا يُفشل المعالجة
        stats["cog"] = {"written": False, "reason": str(_e)}
    meta = {
        "cog_url": cog_url,
        "cog_crs": cog_crs,
        "srid": (src_crs.to_epsg() if src_crs is not None else 4326),
        "nodata": None,  # RGBA يستخدم قناة ألفا لا قيمة nodata
    }
    return stats, bounds, res_m, meta


def _process_pixels(req: ProcessRequest, layer_id: str):
    """المعالجة الفعليّة للبكسلات (تعمل عند توفّر rasterio). تُرجع
    (stats, bounds_4326, resolution_m, meta) حيث meta يحوي cog_url/cog_crs/
    srid/nodata. تطبّق القصّ على الحقل + قناع الغيوم + إعادة إسقاط الحدود."""
    import numpy as np
    import rasterio

    formula = _INDICATOR_FORMULAS[req.indicator.value]
    with rasterio.open(_safe_raster_source(req.raster_url)) as src:
        res_m = abs(src.res[0])
        b = req.bands

        # ── (٣) إعادة إسقاط الحدود إلى WGS84 الحقيقي ──────────────────
        # المصدر غالباً UTM (Sentinel-2 L2A). نحوّل حدوده الفعليّة من CRS
        # المصدر إلى EPSG:4326 بدل تمرير إحداثيّات UTM كأنّها درجات.
        from rasterio.warp import transform_bounds

        src_crs = src.crs
        if src_crs is not None:
            bounds = list(transform_bounds(src_crs, "EPSG:4326", *src.bounds))
        else:
            bounds = list(src.bounds)

        # ── (١) قصّ على حدود الحقل (clip-to-field) ────────────────────
        # عند توفّر مضلّع الحقل (GeoJSON بـEPSG:4326) نعيد إسقاطه إلى CRS
        # المصدر ونطبّق rasterio.mask.mask(crop=True) فنقرأ بكسلات الحقل
        # فقط؛ البكسلات خارج المضلّع تصبح nodata (→ NaN لاحقاً).
        nodata_val = src.nodata if src.nodata is not None else -9999.0
        clip_geom_src = None
        _out = {"transform": src.transform}  # حاوية قابلة للتعديل من band()
        if req.clip_polygon_geojson:
            from rasterio.warp import transform_geom

            geojson = req.clip_polygon_geojson
            # اقبل Feature / FeatureCollection / Geometry
            geom_in = geojson
            if geojson.get("type") == "Feature":
                geom_in = geojson["geometry"]
            elif geojson.get("type") == "FeatureCollection":
                geom_in = geojson["features"][0]["geometry"]
            # تحقّق من صلاحيّة المضلّع عبر shapely (يرمي عند فساده)
            from shapely.geometry import shape as _shape

            _ = _shape(geom_in)  # يتحقّق من البنية الهندسيّة
            target_crs = src_crs if src_crs is not None else "EPSG:4326"
            clip_geom_src = transform_geom("EPSG:4326", target_crs, geom_in)

        from rasterio.mask import mask as _rio_mask

        def _refl_params(idx):
            """(scale, offset) لتحويل DN→انعكاس: تجاوز الطلب أوّلاً، وإلّا المُعلَن في الراستر.

            صدق: لا يُطبَّق إلّا ما هو مُعلَن أو مُمرَّر صراحةً — لا تخمين. هويّة (1,0) ⇒ لا تغيير.
            """
            scale = req.reflectance_scale
            offset = req.reflectance_offset
            if scale is None and src.scales:  # scale/offset المُعلَن في GDAL (per-band)
                scale = src.scales[idx - 1]
            if offset is None and src.offsets:
                offset = src.offsets[idx - 1]
            return scale, offset

        def band(idx):
            """يقرأ نطاقاً كـfloat32 مع قصّ اختياري + تحويل DN→انعكاس [0,1]."""
            if not idx:
                return None
            if clip_geom_src is not None:
                arr_b, t = _rio_mask(
                    src,
                    [clip_geom_src],
                    crop=True,
                    filled=True,
                    nodata=nodata_val,
                    indexes=[idx],
                )
                _out["transform"] = t
                a = arr_b[0].astype("float32")
            else:
                a = src.read(idx).astype("float32")
            # حوّل nodata إلى NaN كي لا يلوّث حساب المؤشّر (قبل المقياس كي لا يُزاح الحارس)
            if src.nodata is not None:
                a = np.where(a == src.nodata, np.nan, a)
            a = np.where(a == nodata_val, np.nan, a)
            # تحويل DN→انعكاس [0,1] لصحّة المؤشّرات المعتمِدة على المقياس (EVI/SAVI/MSAVI).
            _sc, _of = _refl_params(idx)
            a = band_math.to_reflectance(a, _sc, _of, np)
            return a

        def band_raw(idx):
            """يقرأ نطاقاً (مثل SCL) دون تحويل nodata→NaN، مع نفس القصّ."""
            if not idx:
                return None
            if clip_geom_src is not None:
                arr_b, _t = _rio_mask(
                    src,
                    [clip_geom_src],
                    crop=True,
                    filled=True,
                    nodata=0,
                    indexes=[idx],
                )
                return arr_b[0]
            return src.read(idx)

        red = band(b.red)
        nir = band(b.nir)
        green = band(b.green)
        blue = band(b.blue)
        swir1 = band(b.swir1)
        rededge = band(b.rededge) if b.rededge is not None else None
        swir2 = band(b.swir2) if b.swir2 is not None else None
        np.seterr(divide="ignore", invalid="ignore")
        ind = req.indicator.value
        if ind in band_math.NEW_INDEX_BANDS:
            # المؤشّرات الموسّعة (ndre/evi/msavi/moisture) — صيغ نقيّة مختبَرة
            # في band_math.py (مصدر واحد للحقيقة، يُعيد استخدام نفس قراءة النطاق).
            arr = band_math.compute(
                ind,
                {
                    "red": red,
                    "nir": nir,
                    "green": green,
                    "blue": blue,
                    "swir1": swir1,
                    "rededge": rededge,
                },
                np,
            )
        elif ind == "ndvi":
            _d = nir + red
            arr = (nir - red) / np.where(_d == 0, 1e-10, _d)  # حماية القسمة (اتّساقاً مع vari/gli)
        elif ind == "gndvi":
            _d = nir + green
            arr = (nir - green) / np.where(_d == 0, 1e-10, _d)
        elif ind == "reci":
            if rededge is None:
                raise HTTPException(400, "مؤشّر RECI يحتاج نطاق الحافّة الحمراء B05")
            arr = (nir / np.where(rededge == 0, 1e-10, rededge)) - 1.0
        elif ind == "gci":
            arr = (nir / np.where(green == 0, 1e-10, green)) - 1.0
        elif ind == "arvi":
            rb = 2 * red - blue
            _d = nir + rb
            arr = (nir - rb) / np.where(_d == 0, 1e-10, _d)
        elif ind == "sipi":
            _d = nir - red
            arr = (nir - blue) / np.where(_d == 0, 1e-10, _d)
        elif ind == "nbr":
            _d = nir + swir2
            arr = (nir - swir2) / np.where(_d == 0, 1e-10, _d)
        elif ind == "ccci":
            if rededge is None:
                raise HTTPException(400, "مؤشّر CCCI يحتاج نطاق الحافّة الحمراء B05")
            ndre_d = nir + rededge
            ndvi_d = nir + red
            ndre_v = (nir - rededge) / np.where(ndre_d == 0, 1e-10, ndre_d)
            ndvi_v = (nir - red) / np.where(ndvi_d == 0, 1e-10, ndvi_d)
            arr = ndre_v / np.where(ndvi_v == 0, 1e-10, ndvi_v)
        elif ind == "msi":
            # Moisture Stress Index: SWIR1/NIR (أعلى = إجهاد مائي أكبر)
            arr = swir1 / np.where(nir == 0, 1e-10, nir)
        elif ind == "ndwi":
            _d = green + nir
            arr = (green - nir) / np.where(_d == 0, 1e-10, _d)
        elif ind == "ndmi":
            _d = nir + swir1
            arr = (nir - swir1) / np.where(_d == 0, 1e-10, _d)
        elif ind == "savi":
            arr = 1.5 * (nir - red) / (nir + red + 0.5)
        elif ind == "vari":
            # حماية القسمة: المقام قد يبلغ صفراً (green+red=blue) → epsilon
            _denom = green + red - blue
            arr = (green - red) / np.where(_denom == 0, 1e-10, _denom)
        elif ind == "gli":
            # حماية القسمة: المقام قد يبلغ صفراً (نادر) → epsilon
            _denom = 2 * green + red + blue
            arr = (2 * green - red - blue) / np.where(_denom == 0, 1e-10, _denom)
        elif ind == "tgi":
            arr = green - 0.39 * red - 0.61 * blue
        elif ind in ("bsi", "bi", "bi2", "ndti", "dbsi", "ndsi", "satvi"):
            # مؤشّرات التربة — من soil_indices.py
            import soil_indices as si

            if ind == "bsi":
                arr = si.compute_bsi(blue, red, nir, swir2, np)
            elif ind == "bi":
                arr = si.compute_bi(red, green, np)
            elif ind == "bi2":
                arr = si.compute_bi2(red, green, nir, np)
            elif ind == "ndti":
                arr = si.compute_ndti(swir1, swir2, np)
            elif ind == "dbsi":
                _d = nir + red
                _ndvi = (nir - red) / np.where(
                    _d == 0, 1e-10, _d
                )  # حماية القسمة (اتّساقاً مع المؤشّرات أعلاه)
                arr = si.compute_dbsi(green, swir1, _ndvi, np)
            elif ind == "ndsi":
                arr = si.compute_ndsi(swir1, swir2, np)
            else:  # satvi
                arr = si.compute_satvi(red, swir1, swir2, np)
        else:  # fapar تقريب من ndvi
            _d = nir + red
            # حماية القسمة: بكسل أسود/ماء عميق (nir+red=0) كان يعطي nan/inf، وclip
            # كان يحوّل inf→fapar=1 خاطئة فيفسد المتوسّط بصمت. الآن →0 (لا غطاء).
            ndvi = (nir - red) / np.where(_d == 0, 1e-10, _d)
            arr = np.clip(1.24 * ndvi - 0.168, 0, 1)

        # ── (٢) قناع الغيوم (SCL + CLM/CLP s2cloudless) ────────────────
        # أفضل الممارسات: لا نعتمد SCL وحده عندما تتوفر CLM/CLP؛ ندمج SCL
        # مع قناع/احتمالية s2cloudless. SCL أصناف الغيوم/الظلال = {3,8,9,10,11}.
        cloud_pct = None
        cloud_mask_sources: list[str] = []
        if req.apply_cloud_mask:
            masks = []
            if b.scl is not None:
                scl = band_raw(b.scl)
                if scl is not None and scl.shape == arr.shape:
                    masks.append(np.isin(scl, [3, 8, 9, 10, 11]))
                    cloud_mask_sources.append("SCL")
                else:
                    logger.warning(
                        "cloud mask requested but SCL band could not be read or shape mismatched for layer %s",
                        layer_id,
                    )
            if b.clm is not None:
                clm = band_raw(b.clm)
                if clm is not None and clm.shape == arr.shape:
                    masks.append(clm.astype("float32") > 0)
                    cloud_mask_sources.append("CLM")
                else:
                    logger.warning(
                        "cloud mask requested but CLM band could not be read or shape mismatched for layer %s",
                        layer_id,
                    )
            if b.clp is not None:
                clp = band_raw(b.clp)
                if clp is not None and clp.shape == arr.shape:
                    clp_f = clp.astype("float32")
                    # Accept both 0..1 and 0..100 probability encodings.
                    threshold = 0.40 if float(np.nanmax(clp_f)) <= 1.0 else 40.0
                    masks.append(clp_f >= threshold)
                    cloud_mask_sources.append("CLP")
                else:
                    logger.warning(
                        "cloud mask requested but CLP band could not be read or shape mismatched for layer %s",
                        layer_id,
                    )
            if masks:
                cloud_classes = masks[0]
                for m in masks[1:]:
                    cloud_classes = np.logical_or(cloud_classes, m)
                cloud_pct = float(np.mean(cloud_classes) * 100.0) if cloud_classes.size else None
                arr = np.where(cloud_classes, np.nan, arr)
            else:
                logger.warning(
                    "cloud mask requested but no SCL/CLM/CLP quality band is available for layer %s; proceeding unmasked",
                    layer_id,
                )

        valid = np.isfinite(arr)
        vals = arr[valid]
        quality = _quality_from_cloud_pct(cloud_pct, masked=bool(cloud_pct is not None))
        stats = {
            "min": float(np.min(vals)) if vals.size else 0.0,
            "max": float(np.max(vals)) if vals.size else 0.0,
            "mean": float(np.mean(vals)) if vals.size else 0.0,
            "std": float(np.std(vals)) if vals.size else 0.0,
            "valid_pixels": int(valid.sum()),
            "nodata_pixels": int((~valid).sum()),
            "cloud_pct": cloud_pct,
            "cloud_mask_applied": bool(cloud_pct is not None),
            "cloud_mask_sources": cloud_mask_sources,
            "confidence": quality["confidence"],
            "quality": quality["quality"],
            "quality_reason": quality["reason"],
        }
        # احفظ المؤشّر المحسوب كـCOG محسّن (ضغط + بلاطات + أهرامات) — تحسين
        # التخزين: حجم أصغر + قراءة جزئيّة أسرع (TiTiler/MapLibre). نحفظ المؤشّر
        # المقصوص بـtransform المقصوص (out) وبـCRS المصدر الأصلي (UTM غالباً).
        cog_url = None
        cog_crs = str(src_crs or "EPSG:4326")
        try:
            import cog_writer

            cog_uid = uuid.uuid4().hex[:8]
            cog_path = os.path.join(UPLOAD_DIR, f"{req.indicator.value}_{cog_uid}.tif")
            cog_info = cog_writer.write_cog(
                arr, cog_path, _out["transform"], crs=cog_crs, nodata=RASTER_NODATA
            )
            stats["cog"] = cog_info
            if cog_info.get("written"):
                # (٤) خزّن مسار COG كـURI كي يجده tilejson + شبكة المؤشّر.
                # عند ضبط S3 يُرفع الـCOG ويُخزَّن s3://؛ وإلّا يبقى file:// كما هو.
                cog_url = object_store.upload_cog(
                    cog_path,
                    f"{req.field_id or 'nofield'}/{req.indicator.value}_{cog_uid}.tif",
                )
        except Exception as _e:  # noqa: BLE001 — حفظ COG اختياري لا يُفشل الحساب
            stats["cog"] = {"written": False, "reason": str(_e)}
        _ = formula  # موثّق أعلاه
        meta = {
            "cog_url": cog_url,
            "cog_crs": cog_crs,
            "srid": (src_crs.to_epsg() if src_crs is not None else 4326),
            "nodata": RASTER_NODATA,
        }
        return stats, bounds, res_m, meta


class ProcessFromStacRequest(BaseModel):
    """مدخل المعالجة من مشهد STAC متعدّد الملفّات (COG لكلّ نطاق)."""

    tenant_id: str | None = None
    indicator: IndicatorKind = IndicatorKind.ndvi
    band_hrefs: dict[str, str]  # {"red": url, "nir": url, "scl": url, ...}
    scene_id: str | None = None
    capture_datetime: str | None = None
    apply_cloud_mask: bool = True
    clip_polygon_geojson: dict | None = None
    source_format: SourceFormat = SourceFormat.sentinel2_l2a
    geometry_revision: int | None = None  # v143 (FINDING-004): نَسَب هندسة الحقل


# ─── CDSE (Copernicus Data Space) — المزوّد الافتراضيّ + fallback إلى Element84 ──
# CDSE أقوى: يحسب المؤشّر خادميّاً (evalscript على نطاقات Sentinel-2 L2A الكاملة، فسيفساء
# أقلّ غيوماً) فيعيد GeoTIFF نطاق-واحد جاهزاً → مسار precomputed_index (لا band math).
# المنسّق (api/imagery_automation) يجرّبه أوّلاً ثمّ يسقط إلى Element84 عند تعذّره. صدق:
# بلا اعتمادات ⇒ available=false ⇒ يسقط المنسّق بصمت (لا كسر، لا تلفيق).
class ProcessCdseRequest(BaseModel):
    """مدخل معالجة CDSE: bbox + هندسة + مؤشّرات + نافذة زمنيّة."""

    tenant_id: str | None = None
    indicators: list[str] = ["ndvi"]
    bbox: list[float]  # [west, south, east, north] بـEPSG:4326
    geometry: dict | None = None  # Polygon GeoJSON (قصّ على الحقل)
    lookback_days: int = 30
    max_cloud_pct: float = 40.0
    # Optional explicit scene/date window. When set, CDSE processing must not
    # silently use a different "latest" mosaic, because the UI date selector and
    # tile cache depend on acquisition_date matching the requested scene.
    date_from: str | None = None
    date_to: str | None = None
    geometry_revision: int | None = None  # v143 (FINDING-004): نَسَب هندسة الحقل


def _run_cdse_processing(job_id: str, field_id: str, req: ProcessCdseRequest):
    """يحسب مؤشّرات CDSE (evalscript خادميّ) لكلّ مؤشّر ثمّ يسجّلها كطبقات (precomputed).

    لكلّ مؤشّر: Process API → GeoTIFF → ملفّ → ``_run_processing`` بمسار precomputed
    (قراءة نطاق-واحد + COG + persist + provenance). عزل لكلّ مؤشّر (فشل واحد لا يُسقط الباقي).
    """
    import cdse_client

    job = _jobs.get(job_id) or {"job_id": job_id}
    job["status"] = JobStatus.processing
    job["started_at"] = datetime.now(UTC).isoformat()
    _jobs.set(job_id, job)

    dt_to = datetime.now(UTC)
    dt_from = dt_to - timedelta(days=max(int(req.lookback_days), 1))

    def _day_window(value: str | None) -> tuple[str, str] | None:
        if not value:
            return None
        day = str(value)[:10]
        if len(day) != 10:
            return None
        return f"{day}T00:00:00Z", f"{day}T23:59:59Z"

    explicit_from = req.date_from or req.date_to
    explicit_to = req.date_to or req.date_from
    if explicit_from or explicit_to:
        # Bare YYYY-MM-DD must mean the full acquisition day, not a zero-length
        # 00:00→00:00 interval. Zero-length timeRange can cause CDSE 400/empty
        # processing and can make the UI fall back to stale/latest tiles.
        from_day = str(explicit_from or explicit_to)[:10]
        to_day = str(explicit_to or explicit_from)[:10]
        if len(from_day) == 10 and len(to_day) == 10:
            time_from = f"{from_day}T00:00:00Z"
            time_to = f"{to_day}T23:59:59Z"
            capture_datetime = f"{to_day}T12:00:00Z"
        else:
            time_from = cdse_client._to_rfc3339(explicit_from or explicit_to)
            time_to = cdse_client._to_rfc3339(explicit_to or explicit_from)
            capture_datetime = time_to
        scene_id = f"cdse:{str(capture_datetime)[:10]}"
    else:
        # Search Catalog first to bind processing to a real acquisition date.
        # Without this, Process API may return a least-cloud mosaic from the
        # lookback window while we persist acquisition_date=time_to (today),
        # making available-dates and selected tile dates point at the wrong COG.
        time_from = dt_from.strftime("%Y-%m-%dT00:00:00Z")
        time_to = dt_to.strftime("%Y-%m-%dT23:59:59Z")
        capture_datetime = time_to
        scene_id = "cdse:latest"

    client = cdse_client.get_client()
    if not (explicit_from or explicit_to):
        try:
            scenes = client.search_scenes(
                bbox=req.bbox,
                time_from=time_from,
                time_to=time_to,
                max_cloud_pct=req.max_cloud_pct,
                limit=10,
                geometry=req.geometry,
            )
            ranked = _rank_scenes(scenes, max_cloud_pct=req.max_cloud_pct) if scenes else []
            best = ranked[0] if ranked else None
            if best:
                capture_datetime = (
                    best.get("datetime") or best.get("properties", {}).get("datetime") or time_to
                )
                scene_id = (
                    best.get("item_id") or best.get("id") or f"cdse:{str(capture_datetime)[:10]}"
                )
                daywin = _day_window(capture_datetime)
                if daywin:
                    time_from, time_to = daywin
        except Exception as e:  # noqa: BLE001
            logger.warning("CDSE scene date binding skipped; using lookback window: %s", e)

    supported = cdse_client.supported_indices()
    results: dict[str, str] = {}
    failed: dict[str, str] = {}
    # v9-F1: «نجاح» المؤشّر لا يعني بالضرورة الحفظ في DB. نفصل الحفظ الفعليّ عن اكتمال
    # المعالجة كي لا يُعلن اللوج «5 نجح» بينما لم يُحفَظ أيّ صفّ في raster_assets.
    persisted_indices: dict[str, bool] = {}
    total = max(len(req.indicators), 1)
    for i, ind in enumerate(req.indicators):
        if ind not in supported:
            failed[ind] = "unsupported_index"
            continue
        try:
            tiff = client.process_index(
                index=ind,
                bbox=req.bbox,
                time_from=time_from,
                time_to=time_to,
                geometry=req.geometry,
                max_cloud_pct=req.max_cloud_pct,
            )
            if not tiff:
                failed[ind] = "empty_response"
                continue
            tif_path = os.path.join(UPLOAD_DIR, f"cdse_{ind}_{uuid.uuid4().hex[:8]}.tif")
            with open(tif_path, "wb") as fh:
                fh.write(tiff)
            preq = ProcessRequest(
                tenant_id=req.tenant_id or "",
                field_id=field_id,
                raster_url=tif_path,
                indicator=IndicatorKind(ind),
                source_format=SourceFormat.sentinel2_l2a,
                bands=BandMapping(),
                precomputed_index=True,
                provider="cdse",
                scene_id=f"{scene_id}:{ind}",
                capture_datetime=capture_datetime,
                clip_polygon_geojson=req.geometry,
                apply_cloud_mask=False,  # CDSE قنّع الغيوم خادميّاً (dataMask + maxCloudCoverage)
                geometry_revision=req.geometry_revision,  # v143: نَسَب الهندسة (المسار الافتراضيّ)
            )
            sub_job_id = f"{job_id}_{ind}"
            _run_processing(sub_job_id, preq)
            sj = _jobs.get(sub_job_id) or {}
            if sj.get("status") == JobStatus.completed:
                _sres = sj.get("result") or {}
                results[ind] = _sres.get("layer_id") or sub_job_id
                # v9-F1: نُسجّل هل حُفِظ الأصل في DB فعلاً (لا مجرّد اكتمال المعالجة).
                persisted_indices[ind] = bool(_sres.get("persisted") is True)
            else:
                failed[ind] = sj.get("error_message", "unknown")
        except Exception as e:  # noqa: BLE001 — عزل لكلّ مؤشّر (فشل CDSE → يُسجَّل)
            failed[ind] = type(e).__name__
        job["progress_pct"] = int((i + 1) / total * 100)
        _jobs.set(job_id, job)

    job["status"] = JobStatus.completed if results else JobStatus.failed
    job["finished_at"] = datetime.now(UTC).isoformat()
    job["provider"] = "cdse"
    job["cdse_results"] = results
    job["cdse_failed"] = failed
    # v9-F1: صدق الحفظ — العدّاد الحقيقيّ هو ما حُفِظ في DB لا ما اكتملت معالجته.
    _persisted_count = sum(1 for v in persisted_indices.values() if v)
    job["cdse_persisted"] = persisted_indices
    job["cdse_persisted_count"] = _persisted_count
    _jobs.set(job_id, job)
    logger.info(
        "cdse %s: %d اكتمل (%d محفوظ في DB)، %d فشل",
        job_id,
        len(results),
        _persisted_count,
        len(failed),
    )


# بلاطة شفّافة 1×1 (PNG) — عند غياب البلاطة الفعليّة (بلا rasterio)
# FIX: السلسلة السابقة كانت بطول فردي (137 خانة ⇒ 68.5 بايت) فيفشل
# bytes.fromhex عند الاستيراد ويتعطّل إقلاع الخدمة بالكامل. هذه بلاطة
# PNG شفّافة 1×1 صحيحة (68 بايت، CRC سليمة، مُولّدة عبر zlib).
_TRANSPARENT_PNG = bytes.fromhex(
    # 1×1 RGBA fully transparent PNG.  Keep this exact: Leaflet/MapLibre use it
    # for missing raster/index tiles so absent data never paints black stripes.
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f"
    "15c4890000000d49444154789c6360606060000000050001a5f64540000000"
    "0049454e44ae426082"
)

# Finite nodata used in generated COGs. NaN nodata can produce unstable GDAL masks/overviews.
RASTER_NODATA = -9999.0


# ─── دورة حياة الراستر (سدّ فجوة: لا سياسة تنظيف) ──────────────────────


# ─── حزم offline (MBTiles) للمناطق ضعيفة الاتّصال — سدّ فجوة اليمن ──────
OFFLINE_PACKS_DIR = os.path.join(UPLOAD_DIR, "offline_packs")
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


class PrescriptionRequest(BaseModel):
    index: str = "ndvi"
    date: str = "latest"
    grid: int = Field(32, ge=2, le=256)
    n_zones: int = Field(3, ge=2, le=6)
    base_rate: float | None = None  # معدّل أساسي (سماد/بذار) لاشتقاق معدّل المناطق
    strategy: str = "compensate"  # compensate | protect


# ─── كشف التغيّر المكاني بين تاريخين (field-scoped) ───────────────────
class FieldChangeRequest(BaseModel):
    index: str = "ndvi"
    date_a: str  # التاريخ الأقدم (before)
    date_b: str  # التاريخ الأحدث (after)
    grid: int = Field(32, ge=2, le=256)
    slight_threshold: float = 0.1
    severe_threshold: float = 0.2


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
class SalinityClassifyRequest(BaseModel):
    ndsi: float


class SalinityFitRequest(BaseModel):
    samples: list[dict]  # [{"ndsi","ece_ds_m","extraction_method"}]


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
# CDSE) فيُحلّ الاستيراد الدائريّ — وحدات routers تستورد رموزاً من main عبر main.X.
# يضمّ register_routers أيضاً routers/cdse_tiles.py تلقائيّاً (لا تضمين يدويّ).
from router_registry import register_routers  # noqa: E402

register_routers(app)
