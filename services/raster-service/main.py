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
import re
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlparse

import band_math
import httpx
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


def _scene_datetime(scene: dict | SceneCandidate) -> datetime | None:
    val = scene.datetime if isinstance(scene, SceneCandidate) else scene.get("datetime")
    if not val:
        props = (
            scene.properties if isinstance(scene, SceneCandidate) else scene.get("properties") or {}
        )
        val = props.get("datetime") or props.get("acquisition_datetime")
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00")).astimezone(UTC)
    except Exception:  # noqa: BLE001 — تحليل تاريخ اختياريّ؛ أيّ قيمة غير صالحة تُعاد None بأمان
        return None


def _scene_to_dict(scene: dict | SceneCandidate) -> dict:
    return scene.model_dump() if isinstance(scene, SceneCandidate) else dict(scene)


# Agronomic pull policy for core satellite timeline imagery. The values are intentionally
# conservative enough for Yemen/arid operations: do not reject every partially cloudy
# Sentinel-2 scene, but never put scenes with less than 50% clear coverage into the
# default NDVI timeline. >=70% clear is treated as high quality in UI/API metadata.
CORE_TIMELINE_INDICES: set[str] = {"truecolor", "ndvi", "ndre", "ndmi", "msavi", "ndwi", "ndsi"}
NDVI_PULL_MIN_CLEAR_PCT = 50.0
NDVI_PULL_MAX_CLOUD_PCT = 100.0 - NDVI_PULL_MIN_CLEAR_PCT
NDVI_HIGH_QUALITY_CLEAR_PCT = 70.0
NDVI_PULL_MIN_SPACING_DAYS = 3.0
NDVI_PULL_TARGET_SPACING_DAYS = 5.0


def _scene_cloud_pct(scene: dict | SceneCandidate) -> float | None:
    d = _scene_to_dict(scene)
    props = d.get("properties") or {}
    value = d.get("aoi_cloud_pct")
    if value is None:
        value = d.get("cloud_cover_pct", props.get("eo:cloud_cover", props.get("cloud_cover")))
    try:
        return max(0.0, min(100.0, float(value))) if value is not None else None
    except Exception:  # noqa: BLE001
        return None


def _scene_clear_pct(scene: dict | SceneCandidate) -> float | None:
    cloud = _scene_cloud_pct(scene)
    return (100.0 - cloud) if cloud is not None else None


def _scene_quality_label(scene: dict | SceneCandidate) -> str:
    clear = _scene_clear_pct(scene)
    if clear is None:
        return "unknown"
    if clear >= NDVI_HIGH_QUALITY_CLEAR_PCT:
        return "high"
    if clear >= NDVI_PULL_MIN_CLEAR_PCT:
        return "medium"
    return "cloudy"


def _scene_day_key(scene: dict | SceneCandidate) -> str | None:
    dt = _scene_datetime(scene)
    return dt.date().isoformat() if dt else None


def _select_backfill_scenes_by_policy(
    scenes: list[dict | SceneCandidate],
    *,
    indices: list[str] | None = None,
    max_cloud_pct: float = NDVI_PULL_MAX_CLOUD_PCT,
    limit: int = 8,
    min_spacing_days: float = NDVI_PULL_MIN_SPACING_DAYS,
) -> list[dict]:
    """Select provider scenes for historical backfill using the NDVI timeline policy.

    Contract:
      * NDVI/core timeline pulls accept scenes only when clear_pct >= 50% (cloud <= 50%).
      * Prefer higher-quality scenes first, but keep temporal spacing >=3 days where possible
        so a 3-month pull can produce an actual time series rather than one scene/month.
      * When no NDVI/core index is requested, keep the old ranking behavior but still respect
        the caller's max_cloud_pct.
    """
    requested = {str(i).lower() for i in (indices or [])}
    core_requested = bool(requested & CORE_TIMELINE_INDICES) or not requested
    effective_max_cloud = NDVI_PULL_MAX_CLOUD_PCT if core_requested else float(max_cloud_pct)
    effective_max_cloud = (
        min(float(max_cloud_pct), effective_max_cloud)
        if max_cloud_pct is not None
        else effective_max_cloud
    )
    ranked = _rank_scenes(scenes, max_cloud_pct=effective_max_cloud)

    eligible: list[dict] = []
    for item in ranked:
        cloud = _scene_cloud_pct(item)
        if cloud is not None and cloud > effective_max_cloud:
            continue
        clear = _scene_clear_pct(item)
        item["clear_pct"] = round(clear, 3) if clear is not None else None
        item["quality_label"] = _scene_quality_label(item)
        eligible.append(item)

    selected: list[dict] = []
    selected_dt: list[datetime] = []
    for item in eligible:
        dt = _scene_datetime(item)
        if dt and any(
            abs((dt - prev).total_seconds()) < min_spacing_days * 86400 for prev in selected_dt
        ):
            continue
        selected.append(item)
        if dt:
            selected_dt.append(dt)
        if len(selected) >= max(1, int(limit)):
            break

    # If a month has fewer valid spaced scenes than requested, fill from remaining eligible
    # scenes without duplicating days. This preserves availability in cloudy periods while
    # still preferring the 3-5 day cadence.
    if len(selected) < max(1, int(limit)):
        seen_days = {_scene_day_key(s) for s in selected}
        for item in eligible:
            day = _scene_day_key(item)
            if day in seen_days:
                continue
            selected.append(item)
            seen_days.add(day)
            if len(selected) >= max(1, int(limit)):
                break

    return sorted(selected, key=lambda it: _scene_datetime(it) or datetime.min.replace(tzinfo=UTC))


def _scene_quality_score(
    scene: dict | SceneCandidate,
    *,
    now: datetime | None = None,
    max_cloud_pct: float = 40.0,
    prefer_recent_days: int = 45,
) -> dict:
    """Rank satellite scenes using production-safe, explainable weights.

    Ranking policy:
      • AOI cloud percentage beats scene-level cloud percentage when available.
      • Recent scenes are preferred, but not at the expense of cloudy scenes.
      • Coverage and provider quality are positive signals.
      • View angle is a small penalty when providers expose it.
    """
    d = _scene_to_dict(scene)
    props = d.get("properties") or {}
    cloud = d.get("aoi_cloud_pct")
    cloud_source = "aoi_cloud_pct"
    if cloud is None:
        cloud = d.get("cloud_cover_pct", props.get("eo:cloud_cover", props.get("cloud_cover")))
        cloud_source = "scene_cloud_pct"
    try:
        cloud = float(cloud) if cloud is not None else 100.0
    except Exception:
        cloud = 100.0
    cloud = max(0.0, min(100.0, cloud))
    cloud_score = max(0.0, 1.0 - (cloud / max(float(max_cloud_pct), 1.0)))

    now = now or datetime.now(UTC)
    dt = _scene_datetime(scene)
    if dt:
        age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
        recency_score = max(0.0, 1.0 - age_days / max(float(prefer_recent_days), 1.0))
    else:
        age_days = None
        recency_score = 0.25

    coverage = d.get("coverage_pct", props.get("sahool:coverage_pct", 100.0))
    try:
        coverage_score = max(0.0, min(1.0, float(coverage) / 100.0))
    except Exception:
        coverage_score = 0.75

    provider_quality = d.get("provider_quality", props.get("sahool:quality", None))
    try:
        provider_quality = (
            max(0.0, min(1.0, float(provider_quality))) if provider_quality is not None else 0.75
        )
    except Exception:
        provider_quality = 0.75

    view_angle = d.get("view_angle", props.get("view:off_nadir", 0.0))
    try:
        angle_penalty = min(0.15, max(0.0, float(view_angle)) / 400.0)
    except Exception:
        angle_penalty = 0.0

    score = (
        (0.50 * cloud_score)
        + (0.20 * recency_score)
        + (0.20 * coverage_score)
        + (0.10 * provider_quality)
        - angle_penalty
    )
    score = max(0.0, min(1.0, score))
    return {
        "score": round(score, 4),
        "cloud_pct": round(cloud, 3),
        "cloud_source": cloud_source,
        "age_days": round(age_days, 2) if age_days is not None else None,
        "coverage_score": round(coverage_score, 4),
        "recency_score": round(recency_score, 4),
        "provider_quality": round(provider_quality, 4),
        "view_angle_penalty": round(angle_penalty, 4),
    }


def _rank_scenes(
    scenes: list[dict | SceneCandidate],
    *,
    max_cloud_pct: float = 40.0,
    prefer_recent_days: int = 45,
) -> list[dict]:
    ranked = []
    for scene in scenes:
        d = _scene_to_dict(scene)
        q = _scene_quality_score(
            scene, max_cloud_pct=max_cloud_pct, prefer_recent_days=prefer_recent_days
        )
        d["sahool_quality"] = q
        d["quality_score"] = q["score"]
        ranked.append(d)
    return sorted(
        ranked, key=lambda it: (-float(it.get("quality_score", 0)), it.get("datetime") or "")
    )


# صيانة كاش البلاطات (تعقيم المسار + الإبطال + الإخلاء) في وحدة مستقلّة بلا FastAPI
# كي يستوردها عامل الإبطال بخفّة وتُختبَر بمعزل. نُعيد تصديرها هنا للتوافق.
import tile_cache_maint  # noqa: E402

invalidate_field_tile_cache = tile_cache_maint.invalidate_field_tile_cache
prune_tile_cache = tile_cache_maint.prune_tile_cache
_safe_cache_segment = tile_cache_maint.safe_cache_segment
_tile_cache_field_dir = tile_cache_maint.tile_cache_field_dir


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
    safe = _safe_cache_segment
    return os.path.join(
        UPLOAD_DIR,
        "tile_cache",
        safe(tenant_id),
        safe(field_id),
        safe(index),
        safe(date),
        safe(v or "default"),
        str(z),
        f"{x}_{y}.png",
    )


def _read_tile_cache(path: str) -> bytes | None:
    if os.getenv("TILE_CACHE_ENABLED", "true").lower() != "true":
        return None
    try:
        if os.path.exists(path):
            with open(path, "rb") as fh:
                return fh.read()
    except OSError:
        return None
    return None


def _write_tile_cache(path: str, data: bytes) -> None:
    if os.getenv("TILE_CACHE_ENABLED", "true").lower() != "true" or not data:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
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


def _parse_ymd(value: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"{field_name} يجب أن يكون YYYY-MM-DD") from e


def _backfill_date_range(req: HistoricalBackfillRequest) -> tuple[datetime, datetime, int]:
    end = _parse_ymd(req.to_date, "to_date") if req.to_date else datetime.now(UTC)
    if req.from_date:
        start = _parse_ymd(req.from_date, "from_date")
        months = max(1, (end.year - start.year) * 12 + (end.month - start.month) + 1)
    else:
        months = req.months or _BACKFILL_PRESET_MONTHS.get(req.preset, 12)
        # approximate month arithmetic without external dependency: 31 days is safe for search coverage.
        start = end - timedelta(days=31 * months)
    if start >= end:
        raise HTTPException(400, "from_date يجب أن يسبق to_date")
    if months > 60 and req.preset != HistoricalBackfillPreset.custom:
        raise HTTPException(400, "استخدم preset=custom للفترات الأكبر من 5 سنوات")
    return start, end, months


def _bbox_from_geojson(geojson: dict | None) -> list[float] | None:
    if not geojson:
        return None
    coords: list[tuple[float, float]] = []

    def walk(node):
        if (
            isinstance(node, (list, tuple))
            and len(node) >= 2
            and all(isinstance(v, (int, float)) for v in node[:2])
        ):
            lon, lat = float(node[0]), float(node[1])
            coords.append((lon, lat))
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(geojson.get("coordinates"))
    if not coords:
        return None
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return [min(xs), min(ys), max(xs), max(ys)]


def _month_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    windows = []
    cur = datetime(start.year, start.month, 1, tzinfo=UTC)
    while cur < end:
        nxt = datetime(
            cur.year + (1 if cur.month == 12 else 0),
            1 if cur.month == 12 else cur.month + 1,
            1,
            tzinfo=UTC,
        )
        w_start = max(start, cur)
        w_end = min(end, nxt - timedelta(seconds=1))
        if w_start < w_end:
            windows.append((w_start, w_end))
        cur = nxt
    return windows


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


# ─── بحث الصور عبر Element84 STAC ─────────────────────────────────
def _band_urls_from_assets(assets: dict) -> dict:
    """يستخرج روابط النطاقات من STAC assets (Sentinel-2 L2A على Element84).

    تعيين أسماء Element84 → حقول BandMapping:
      • "rededge1" (B05, 705nm)  → "rededge"  (الأكثر استخداماً لـNDRE)
      • "swir16"   (B11, 1610nm) → "swir1"    (مطلوب لـNDMI / MSI / BSI …)
      • "swir22"   (B12, 2190nm) → "swir2"    (مطلوب لـBSI / SATVI / NDTI …)
    النطاقات الزائدة (rededge2/3، nir08، visual، thumbnail) تُحذف كي لا تنتهي
    في الـVRT كأعداد مجهولة تُفشل الحساب (كانت السبب الجذري لـTypeError في كلّ
    مهامّ backfill التي تحتاج swir1/rededge — بلاغ 2026-07-04).
    """

    def url(key: str) -> str | None:
        a = assets.get(key)
        return a.get("href") if a else None

    return {
        "blue": url("blue"),
        "green": url("green"),
        "red": url("red"),
        "nir": url("nir"),
        "rededge": url("rededge1"),   # B05 → BandMapping.rededge (NDRE / red-edge)
        "swir1": url("swir16"),       # B11 → BandMapping.swir1   (NDMI / MSI / BSI)
        "swir2": url("swir22"),       # B12 → BandMapping.swir2   (BSI / SATVI / NDTI)
        "scl": url("scl"),
    }


async def _stac_query(payload: dict) -> dict:
    """يستدعي العميل المرن ويحوّل الفشل التامّ إلى 503 صادق (لا 500 خام).

    RuntimeError من ResilientStacClient = الأساس + كلّ الاحتياطيّات فشلوا ولا
    cache (بلاغ 2026-07-04: DNS الحاوية معطّل — Errno -5 حتى للاحتياطيّ) — خطأ
    بنية تحتيّة لا خطأ في خادمنا، فيُبلَّغ 503 برسالة ثابتة قابلة للتصرّف بدل
    traceback يخرج للعميل 500. التفصيل الخام يبقى في السجلّ الداخليّ فقط.
    """
    try:
        return await _stac.search(payload)
    except RuntimeError as e:
        logger.error("STAC غير متاح (collections=%s): %s", payload.get("collections"), e)
        raise HTTPException(
            503,
            "فهرس صور الأقمار (STAC) غير متاح حاليّاً من داخل الخدمة — "
            "تحقّق من اتّصال/DNS حاوية raster-service ثمّ أعد المحاولة",
        ) from e


async def _stac_search(
    bbox: list[float],
    dt_start: str,
    dt_end: str,
    max_cloud: float,
    limit: int,
    geometry: dict | None = None,
) -> dict:
    """يبحث عن مشاهد Sentinel-2 التاريخيّة — CDSE افتراضاً (Copernicus).

    التحويل الكامل: ``HISTORICAL_SEARCH_PROVIDER=cdse`` (الافتراض) يستعمل كتالوج
    CDSE (Sentinel Hub Catalog) للاكتشاف — نفس مصدر المعالجة (process_index)، فلا
    اعتماد على Element84 Earth Search في المسار التاريخيّ.

    الإغلاق الآمن (بطلب المستخدم — «بالكامل من Copernicus»): عند اختيار مزوّد CDSE
    وغياب الاعتمادات لا نرتدّ صامتاً إلى Element84 — نفشل مُغلَقاً بـ503 صريح. الارتداد
    إلى Element84 يقع **فقط** حين ``HISTORICAL_SEARCH_PROVIDER=element84`` صراحةً
    (تجاوز واعٍ لمجموعات/بيئات لا يوفّرها CDSE).
    """
    import cdse_client as _cdse

    if HISTORICAL_SEARCH_PROVIDER == "element84":
        return await _stac_search_element84(bbox, dt_start, dt_end, max_cloud, limit)
    # المزوّد الافتراضيّ = CDSE: لا اعتمادات ⇒ فشل مُغلَق (لا تسرّب صامت إلى Element84).
    if not _cdse.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "بحث الأقمار التاريخيّ يعتمد Copernicus/CDSE حصراً؛ الاعتمادات غائبة "
                "(CDSE_CLIENT_ID/SECRET أو SH_CLIENT_ID/SECRET). اضبطها، أو عيّن "
                "HISTORICAL_SEARCH_PROVIDER=element84 صراحةً لتجاوز واعٍ."
            ),
        )
    return await _stac_search_cdse(bbox, dt_start, dt_end, max_cloud, limit, geometry)


async def _stac_search_cdse(
    bbox: list[float],
    dt_start: str,
    dt_end: str,
    max_cloud: float,
    limit: int,
    geometry: dict | None = None,
) -> dict:
    """اكتشاف مشاهد Sentinel-2 عبر كتالوج CDSE (Sentinel Hub Catalog).

    يُرجِع نفس شكل مخرَج ``_stac_search`` (item_id/datetime/cloud/bbox/platform).
    ``bands_urls`` فارغ عمداً: CDSE يعالج المشهد خادميّاً عبر Process API (بلا روابط
    نطاقات COG)، فمسار المعالجة يستعمل ``process_index`` مثبَّتاً على تاريخ المشهد.
    استدعاء العميل متزامن (httpx) فنُشغّله في threadpool كي لا يحجب حلقة الأحداث.
    """
    import asyncio

    import cdse_client as _cdse

    def _do() -> list[dict]:
        return _cdse.get_client().search_scenes(
            bbox=bbox,
            time_from=dt_start,
            time_to=dt_end,
            max_cloud_pct=max_cloud,
            limit=limit,
            geometry=geometry,
        )

    try:
        features = await asyncio.to_thread(_do)
    except Exception as e:  # noqa: BLE001 — فشل الكتالوج لا يُسقط المسار (قائمة فارغة)
        logger.warning("CDSE catalog search failed: %s", e)
        features = []

    items = []
    for feat in features:
        props = feat.get("properties", {}) or {}
        items.append(
            {
                "item_id": feat.get("id", ""),
                "datetime": props.get("datetime", ""),
                "cloud_cover_pct": props.get("eo:cloud_cover", 0.0),
                "bbox": feat.get("bbox"),
                # CDSE يعالج بالـProcess API (لا نطاقات COG) — فارغ متعمَّد؛ مسار المعالجة
                # يتفرّع على غيابها إلى process_index مثبَّت على تاريخ المشهد.
                "bands_urls": {},
                "thumbnail_url": None,
                "preview_url": None,
                "platform": props.get("platform", "sentinel-2"),
                "provider": "cdse",
            }
        )
    return {
        "count": len(items),
        "source": "cdse-catalog",
        "cache": "miss",
        "warning": None,
        "items": items,
    }


async def _stac_search_element84(
    bbox: list[float], dt_start: str, dt_end: str, max_cloud: float, limit: int
) -> dict:
    """يبحث في Element84 Earth Search عن صور Sentinel-2 (ارتداد/مجموعات غير CDSE).

    يستخدم العميل المرن (stac_client): إعادة محاولة + cache + stale-if-error
    — مرونة تشغيليّة لقلب النظام (مهمّ لبيئة اليمن عالية الـlatency).
    """
    payload = {
        "collections": [SENTINEL_COLLECTION],
        "bbox": bbox,
        "datetime": f"{dt_start}/{dt_end}",
        "query": {"eo:cloud_cover": {"lte": max_cloud}},
        "limit": limit,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    data = await _stac_query(payload)

    items = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        assets = feat.get("assets", {})
        items.append(
            {
                "item_id": feat.get("id", ""),
                "datetime": props.get("datetime", ""),
                "cloud_cover_pct": props.get("eo:cloud_cover", 0.0),
                "bbox": feat.get("bbox"),
                "bands_urls": _band_urls_from_assets(assets),
                "thumbnail_url": (assets.get("thumbnail") or {}).get("href"),
                "preview_url": (assets.get("visual") or {}).get("href"),
                "platform": props.get("platform", "sentinel-2"),
                "provider": "element84",
            }
        )
    return {
        "count": len(items),
        "source": "element84-earth-search",
        "cache": data.get("_cache", "miss"),
        "warning": data.get("_warning"),
        "items": items,
    }


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


async def _stac_search_radar(bbox: list[float], dt_start: str, dt_end: str, limit: int) -> dict:
    """يبحث عن صور رادار Sentinel-1 GRD عبر Element84.

    الرادار يختلف جوهريّاً عن البصري:
      • لا فلتر غيوم — الرادار يخترق الغيوم والليل (ميزته الكبرى)
      • النطاقات استقطابات (VV/VH) لا ألوان طيفيّة — تُستخدم لرطوبة التربة،
        كشف الفيضانات، رصد التغيّر البنيوي. لا تصلح لـNDVI.
    مفيد لليمن في موسم الأمطار حين تحجب الغيوم البصري.
    """
    payload = {
        "collections": [SENTINEL1_COLLECTION],
        "bbox": bbox,
        "datetime": f"{dt_start}/{dt_end}",
        "limit": limit,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f"{EARTH_SEARCH_URL}/search", json=payload)
        resp.raise_for_status()
        data = resp.json()

    items = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        assets = feat.get("assets", {})
        # استقطابات الرادار (قد تكون vv وvh أو hh وhv)
        pol_urls = {
            k: (assets.get(k) or {}).get("href") for k in ("vv", "vh", "hh", "hv") if assets.get(k)
        }
        items.append(
            {
                "item_id": feat.get("id", ""),
                "datetime": props.get("datetime", ""),
                "bbox": feat.get("bbox"),
                "polarization_urls": pol_urls,
                "polarizations": props.get("sar:polarizations", list(pol_urls.keys())),
                "orbit_state": props.get("sat:orbit_state"),
                "thumbnail_url": (assets.get("thumbnail") or {}).get("href"),
                "platform": props.get("platform", "sentinel-1"),
                "data_type": "radar",
                "note_ar": "رادار SAR — يخترق الغيوم. لا يُحسب منه NDVI (نطاقات استقطاب لا طيفيّة).",
            }
        )
    return {
        "count": len(items),
        "source": "element84-earth-search",
        "collection": SENTINEL1_COLLECTION,
        "items": items,
    }


def _landsat_thermal_href(assets: dict) -> str | None:
    """اختر أصل LST الحراري فقط من Landsat C2 L2 STAC assets.

    لا نُرجع RED/NIR/SWIR هنا عمداً: هذه مؤشّرات Sentinel-2 المكررة. الهدف أن يبقى
    Landsat في Sahool طبقة حرارية فريدة (LST) تُشتق منها CWSI/TVDI/TCI/VHI لاحقاً.
    """
    for key in LANDSAT_THERMAL_ASSET_CANDIDATES:
        href = (assets.get(key) or {}).get("href") if isinstance(assets.get(key), dict) else None
        if href:
            return href
    # بعض كتالوجات Landsat تستعمل أسماء أطول/مختلفة؛ نقبل فقط ما يصرّح بسطح/حرارة،
    # لا نقبل أصول optical مثل red/nir/swir لتجنّب تكرار مؤشرات Sentinel.
    for key, asset in (assets or {}).items():
        lk = str(key).lower()
        title = str((asset or {}).get("title", "")).lower() if isinstance(asset, dict) else ""
        href = (asset or {}).get("href") if isinstance(asset, dict) else None
        if href and ("surface temperature" in title or "temperature" in lk or "thermal" in lk):
            return href
    return None


def _landsat_unique_payload(feat: dict) -> dict | None:
    props = feat.get("properties", {}) or {}
    assets = feat.get("assets", {}) or {}
    thermal_href = _landsat_thermal_href(assets)
    if not thermal_href:
        return None
    platform = props.get("platform", "landsat")
    return {
        "item_id": feat.get("id", ""),
        "datetime": props.get("datetime", ""),
        "cloud_cover_pct": props.get("eo:cloud_cover", 0.0),
        "bbox": feat.get("bbox"),
        "platform": platform,
        "thumbnail_url": (assets.get("thumbnail") or {}).get("href"),
        "provider": "landsat-element84",
        "data_type": "thermal_unique",
        "thermal_urls": {"lst": thermal_href},
        "direct_indices": sorted(LANDSAT_DIRECT_RASTER_INDICES),
        "derived_indices": sorted(LANDSAT_DERIVED_INDICES),
        "excluded_duplicate_sentinel_indices": sorted(LANDSAT_DUPLICATE_SENTINEL_INDICES),
        "note_ar": (
            "Landsat يُستخدم هنا للطبقة الحرارية الفريدة فقط: LST مباشرة، "
            "ومنها تُشتق CWSI/TVDI/TCI/VHI مع الطقس/NDVI. لا نسحب NDVI/NDMI المكررة من Landsat."
        ),
    }


async def _stac_search_landsat(
    bbox: list[float], dt_start: str, dt_end: str, max_cloud: float, limit: int
) -> dict:
    """بحث Landsat C2 L2 كطبقة حرارية فريدة فقط.

    القرار المعماري: Copernicus/Sentinel-2 هو مصدر NDVI/NDMI/MSI/...؛ Landsat لا يدخل
    لإعادة حساب هذه المؤشرات الأخشن، بل فقط LST والاشتقاقات الحرارية المرتبطة بها.
    """
    return await _stac_search_landsat_unique(bbox, dt_start, dt_end, max_cloud, limit)


async def _stac_search_landsat_unique(
    bbox: list[float], dt_start: str, dt_end: str, max_cloud: float, limit: int
) -> dict:
    payload = {
        "collections": [LANDSAT_COLLECTION],
        "bbox": bbox,
        "datetime": f"{dt_start}/{dt_end}",
        "query": {"eo:cloud_cover": {"lte": max_cloud}},
        "limit": limit,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    data = await _stac_query(payload)
    items = []
    for feat in data.get("features", []):
        item = _landsat_unique_payload(feat)
        if item is not None:
            items.append(item)
    return {
        "count": len(items),
        "source": "element84-earth-search",
        "collection": LANDSAT_COLLECTION,
        "provider_role": "landsat_thermal_unique_only",
        "cache": data.get("_cache"),
        "unique_indices": sorted(LANDSAT_UNIQUE_INDICES),
        "direct_raster_indices": sorted(LANDSAT_DIRECT_RASTER_INDICES),
        "derived_indices_require": {
            "cwsi": ["lst", "air_temperature", "relative_humidity_or_vpd", "wet_dry_reference"],
            "tvdi": ["lst", "ndvi"],
            "tci": ["lst", "historical_lst_min_max"],
            "vhi": ["tci", "vci_from_ndvi_history"],
            "et_inputs": ["lst", "albedo_or_reflectance", "ndvi", "weather"],
        },
        "excluded_duplicate_sentinel_indices": sorted(LANDSAT_DUPLICATE_SENTINEL_INDICES),
        "items": items,
    }


async def _stac_search_dem(bbox: list[float]) -> dict:
    """يبحث عن بلاطات Copernicus DEM (نموذج ارتفاع رقمي) لمنطقة.

    DEM لا زمني (ثابت) — لا datetime/cloud. يُستخدَم لحساب الانحدار/الصرف/
    حصاد المياه (حرج لزراعة اليمن المُدرّجة الصحراويّة). دقّة 30م، COG، مجّاني.
    """
    payload = {
        "collections": [DEM_COLLECTION],
        "bbox": bbox,
        "limit": 20,
    }
    data = await _stac_query(payload)
    items = []
    for feat in data.get("features", []):
        assets = feat.get("assets", {})
        items.append(
            {
                "item_id": feat.get("id", ""),
                "bbox": feat.get("bbox"),
                "dem_url": (assets.get("data") or assets.get("elevation") or {}).get("href"),
                "data_type": "elevation",
                "resolution_m": 30,
                "note_ar": "نموذج ارتفاع 30م — للانحدار/الصرف/حصاد المياه. ثابت لا زمني.",
            }
        )
    return {
        "count": len(items),
        "source": "element84-earth-search",
        "collection": DEM_COLLECTION,
        "cache": data.get("_cache"),
        "items": items,
    }


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


def _is_valid_uuid_text(value: str | None) -> bool:
    if not value or not str(value).strip():
        return False
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


# معرّف الحقل القانونيّ نصّيّ (fld_<hex>) والعمود raster_assets.field_id هو
# VARCHAR(50) لا UUID — فرضُ UUID عليه أسقط الحفظ لكلّ حقل حقيقيّ بصمت
# (بلاغ 2026-07-04). tenant_id يبقى UUID (عموده UUID فعلاً — قصد تصليب 06-26).
_FIELD_ID_TEXT_RE = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


def _is_valid_field_id_text(value: str | None) -> bool:
    """معرّف حقل آمن لعمود VARCHAR(50): fld_* أو UUID — لا فارغ/محارف غريبة."""
    return bool(value) and bool(_FIELD_ID_TEXT_RE.fullmatch(str(value).strip()))


def _persist_raster_asset(
    req: ProcessRequest,
    cog_url: str,
    meta: dict,
    bounds: list,
    stats: dict,
    job_id: str | None = None,
) -> bool:
    """يُدرج صفّاً في raster_assets (best-effort). يُرجِع True عند الحفظ الفعليّ.

    _run_processing يعمل في threadpool (مهمّة خلفيّة متزامنة) فلا حلقة
    أحداث في خيطه؛ لذا asyncio.run آمن هنا. غياب القاعدة (لا DATABASE_URL/
    لا جدول/لا شبكة) يُبتلع بصدق ولا يُفشل المعالجة (يُرجِع False).
    """
    if not _is_valid_field_id_text(req.field_id):
        logger.warning("raster_assets persist skipped: missing/invalid field_id=%r", req.field_id)
        return False
    if (
        req.tenant_id is not None
        and str(req.tenant_id).strip()
        and not _is_valid_uuid_text(req.tenant_id)
    ):
        logger.warning("raster_assets persist skipped: invalid tenant_id=%r", req.tenant_id)
        return False
    try:
        import asyncio

        import db_persist
        import quality_metrics

        # v131 (v62.3-B): مقاييس جودة الصور من عدّادات البكسلات في stats.
        # valid_pixels/nodata_pixels يوفّرها _process_pixels/_process_precomputed_pixels؛
        # غيابهما (بنية بلا rasterio) ⇒ إجماليّ = 0 ⇒ نسب None (لا اختراع).
        _vp = stats.get("valid_pixels")
        _np = stats.get("nodata_pixels")
        _total = (int(_vp) + int(_np)) if (_vp is not None and _np is not None) else None
        _quality = quality_metrics.compute_quality_metrics(
            valid_pixels=int(_vp) if _vp is not None else None,
            total_pixels=_total,
            cloud_pct=stats.get("cloud_pct"),
        )

        # footprint كـbbox polygon بـ4326 (الحدود معاد إسقاطها)
        minlon, minlat, maxlon, maxlat = bounds[0], bounds[1], bounds[2], bounds[3]
        footprint = {
            "type": "Polygon",
            "coordinates": [
                [
                    [minlon, minlat],
                    [maxlon, minlat],
                    [maxlon, maxlat],
                    [minlon, maxlat],
                    [minlon, minlat],
                ]
            ],
        }

        async def _do():
            ok = await db_persist.insert_raster_asset(
                field_id=req.field_id,
                tenant_id=req.tenant_id,
                scene_id=req.scene_id,
                acquisition_date=req.capture_datetime,
                satellite=req.source_format.value,
                index_name=req.indicator.value,
                cloud_pct=stats.get("cloud_pct"),
                srid=meta.get("srid"),
                cog_uri=cog_url,
                bands=req.bands.model_dump() if hasattr(req.bands, "model_dump") else None,
                nodata=meta.get("nodata"),
                footprint=footprint,
                valid_pixel_ratio=_quality["valid_pixel_ratio"],
                coverage_ratio=_quality["coverage_ratio"],
                index_quality_flags=_quality["index_quality_flags"],
                processing_job_id=job_id,  # v142: تتبّع + يُغني layer_owner_tenant عن ILIKE
                # v105 (v4-audit): أعمدة الجودة تُكتب الآن فعلاً كي يعمل الترتيب الواعي بالجودة.
                # confidence هو الدرجة 0..1 (أعلى=أفضل)؛ cloud_pct محسوب على AOI المقصوص.
                quality_score=stats.get("confidence"),
                aoi_cloud_pct=stats.get("cloud_pct"),
                cloud_mask_sources=stats.get("cloud_mask_sources"),
                # v143 (FINDING-004): مراجعة الهندسة السارية وقت المعالجة (None إن لم تُمرَّر).
                geometry_revision=getattr(req, "geometry_revision", None),
                provenance={
                    "stats": {
                        k: stats.get(k)
                        for k in (
                            "min",
                            "max",
                            "mean",
                            "std",
                            "cloud_pct",
                            "cloud_mask_applied",
                            "cloud_mask_sources",  # v4-audit: كان يُنتَج ويُسقَط من النَّسَب
                            "quality",
                            "confidence",
                        )
                    },
                    # v143: النَّسَب — مراجعة الهندسة في الأصل نفسه (فوق العمود المخصّص).
                    "geometry_revision": getattr(req, "geometry_revision", None),
                },
            )
            # FINDING-008: جسر الكتالوج — عند نجاح الأصل نكتب صفّاً مُقابِلاً في
            # raster_registry (كان يملؤه فقط مسار REST يدويّ) كي لا يبقى الكتالوج فارغاً.
            if ok and cog_url and not str(cog_url).startswith("file://"):
                await db_persist.insert_raster_registry_entry(
                    tenant_id=req.tenant_id,
                    field_id=req.field_id,
                    scene_id=req.scene_id,
                    product_date=req.capture_datetime,
                    index_type=req.indicator.value,
                    cog_url=cog_url,
                    cloud_pct=stats.get("cloud_pct"),
                    quality_score=stats.get("confidence"),
                    resolution_m=meta.get("resolution_m") or 10.0,
                    bbox=list(bounds) if bounds else None,
                    bands=req.bands.model_dump() if hasattr(req.bands, "model_dump") else None,
                    metadata={
                        "quality": stats.get("quality"),
                        "confidence": stats.get("confidence"),
                        "provider": getattr(req, "provider", None),
                        "geometry_revision": getattr(req, "geometry_revision", None),
                    },
                )
            return ok

        # v5-audit F1: نلتقط نتيجة الحفظ ونُصدِر سطراً منظَّماً — «job completed» وحده
        # كان لا يُميّز «حُفِظ في DB» عن «في الذاكرة فقط والإدراج عاد False بصمت»، فبعد
        # إعادة التشغيل قد يفشل الترطيب رغم «completed». الآن persisted صريح في السجلّ والمهمّة.
        _holder = {"ok": False}
        try:
            _holder["ok"] = bool(asyncio.run(_do()))
        except RuntimeError:
            # حلقة أحداث قائمة بالفعل (نادر هنا) — شغّلها في خيط مستقلّ
            import threading

            def _runner():
                _holder["ok"] = bool(asyncio.run(_do()))

            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            # v9-F2: مهلة أوسع (60s) لإدراج DB البطيء. لو تجاوزها الخيط لا نُعلن
            # persisted=false كذباً بل نُصرّح بأنّ النتيجة «غير حاسمة» (قد يكتمل لاحقاً).
            t.join(timeout=60)
            if t.is_alive():
                logger.warning(
                    "raster_assets persist result indeterminate field_id=%s index=%s "
                    "(خيط الإدراج ما زال يعمل بعد 60s — قد يكتمل الحفظ خلفيّاً)",
                    req.field_id,
                    req.indicator.value,
                )
        if _holder["ok"]:
            logger.info(
                "raster_assets persist ok field_id=%s tenant_id=%s index=%s scene_id=%s "
                "acquisition_date=%s cog_uri=%s",
                req.field_id,
                req.tenant_id,
                req.indicator.value,
                req.scene_id,
                req.capture_datetime,
                cog_url,
            )
        else:
            logger.warning(
                "raster_assets persist failed field_id=%s index=%s scene_id=%s "
                "(best-effort؛ COG في الذاكرة/القرص المحلّيّ فقط — قد يفشل الترطيب بعد إعادة التشغيل)",
                req.field_id,
                req.indicator.value,
                req.scene_id,
            )
        return _holder["ok"]
    except Exception as _dbe:  # noqa: BLE001 — صدق: لا نُفشل المعالجة لغياب القاعدة
        logger.warning("raster_assets persist skipped: %s", _dbe)
        return False


def _run_processing(job_id: str, req: ProcessRequest):
    """ينفّذ معالجة المؤشّر. البنية كاملة؛ حساب البكسلات الفعلي يتمّ عند
    توفّر rasterio في بيئة التشغيل (يُحقن هنا)."""
    # نحمّل المهمّة، نطفّرها محليّاً، ونثبّتها في المخزن (Redis/ذاكرة) عند
    # نقاط الانتقال — كي تَنفُذ التغييرات عبر العمليّات لا في dict محلّيّ فقط.
    job = _jobs.get(job_id) or {"job_id": job_id}
    job["status"] = JobStatus.processing
    job["started_at"] = datetime.now(UTC).isoformat()
    job["progress_pct"] = 10
    _jobs.set(job_id, job)
    try:
        # نقطة حقن المعالجة الفعليّة (rasterio/numpy):
        #   1. اقرأ الراستر من req.raster_url
        #   2. طبّق band math حسب _INDICATOR_FORMULAS[req.indicator]
        #   3. طبّق cloud mask (SCL) إن apply_cloud_mask
        #   4. clip بـclip_polygon_geojson
        #   5. أنتج بلاطات (tiling_strategy) واحفظها
        #   6. احسب الإحصاءات (min/max/mean/std)
        try:
            import numpy  # noqa: F401
            import rasterio  # noqa: F401

            _has_raster_libs = True
        except ImportError:
            _has_raster_libs = False

        layer_id = f"layer_{uuid.uuid4().hex[:12]}"
        meta: dict = {}
        if _has_raster_libs and req.raster_url:
            # المعالجة الفعليّة (تتمّ في بيئة التشغيل مع rasterio)
            if req.precomputed_index:
                # CDSE: المؤشّر محسوب خادميّاً — اقرأه نطاقاً واحداً جاهزاً.
                stats, bounds, res_m, meta = _process_precomputed_pixels(req, layer_id)
            else:
                stats, bounds, res_m, meta = _process_pixels(req, layer_id)
        else:
            # بنية بلا حساب فعلي (البيئة بلا rasterio) — ترجع هيكلاً صحيحاً
            stats = {
                "min": 0.0,
                "max": 1.0,
                "mean": 0.0,
                "std": 0.0,
                "valid_pixels": 0,
                "nodata_pixels": 0,
            }
            bounds = [0.0, 0.0, 0.0, 0.0]
            res_m = 10.0
            job["note"] = "rasterio غير متوفّر — بنية صحيحة بلا حساب بكسلات"

        now = datetime.now(UTC).isoformat()
        # provenance (#7): سجلّ أصل كامل لإعادة الإنتاج
        import raster_provenance as _prov

        provenance = _prov.build_provenance(
            req.indicator.value,
            scene_id=req.scene_id,
            capture_datetime=req.capture_datetime,
            raster_url=req.raster_url,
            source_format=req.source_format.value,
            crs="EPSG:4326",
            resolution_m=res_m,
            apply_cloud_mask=req.apply_cloud_mask,
            band_mapping=req.bands.model_dump() if hasattr(req.bands, "model_dump") else None,
            clip_polygon=req.clip_polygon_geojson,
        )
        cog_url = meta.get("cog_url")
        # v131 (v62.3-B): مقاييس جودة الصور للطبقة في الذاكرة كي تسطّحها شبكة
        # المؤشّر مباشرةً دون دورة قاعدة (نفس منطق الكاتب: عدّادات البكسلات من stats).
        import quality_metrics as _qm

        _vp = stats.get("valid_pixels")
        _npx = stats.get("nodata_pixels")
        _tot = (int(_vp) + int(_npx)) if (_vp is not None and _npx is not None) else None
        _layer_q = _qm.compute_quality_metrics(
            valid_pixels=int(_vp) if _vp is not None else None,
            total_pixels=_tot,
            cloud_pct=stats.get("cloud_pct"),
        )
        _cloud_pct = stats.get("cloud_pct")
        _layers[layer_id] = {
            "layer_id": layer_id,
            "field_id": req.field_id,
            "tenant_id": req.tenant_id,
            "index": req.indicator.value,
            "source_format": req.source_format.value,
            "width": 0,
            "height": 0,
            "band_count": 1,
            # CRS الطبقة الفعلي = CRS الـCOG (UTM للـSentinel-2)؛ الحدود معاد
            # إسقاطها إلى 4326 لعرض الخريطة.
            "crs": meta.get("cog_crs", "EPSG:4326"),
            "bounds_4326": bounds,
            "resolution_m": res_m,
            "cog_url": cog_url,  # (٤) كي يجده tilejson + شبكة المؤشّر
            "acquisition_date": req.capture_datetime,
            "provider": req.provider,  # مصدر الصورة (cdse/element84) — شفافيّة الأصل
            "cloud_pct": _cloud_pct,
            "cloud_cover": (_cloud_pct / 100.0) if _cloud_pct is not None else None,
            "valid_pixel_ratio": _layer_q["valid_pixel_ratio"],
            "coverage_ratio": _layer_q["coverage_ratio"],
            "index_quality_flags": _layer_q["index_quality_flags"],
            "cloud_mask_applied": stats.get("cloud_mask_applied"),
            "confidence": stats.get("confidence"),
            "quality": stats.get("quality"),
            "created_at": now,
            "provenance": provenance,
        }
        # فهرس حقل→طبقات (للبحث عن أحدث COG لحقل+مؤشّر في شبكة المؤشّر)
        if req.field_id:
            _field_layers.setdefault(req.field_id, []).append(layer_id)
        # (٦) حفظ في raster_assets (best-effort — غياب القاعدة لا يُفشل المعالجة)
        # v5-audit F1: نلتقط persisted كي يُميّز «completed» بين الحفظ في DB والذاكرة فقط.
        persisted = (
            _persist_raster_asset(req, cog_url, meta, bounds, stats, job_id=job_id)
            if cog_url
            else False
        )
        job["result"] = {
            "job_id": job_id,
            "layer_id": layer_id,
            "indicator": req.indicator.value,
            "stats": stats,
            "tile_url_template": f"/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png",
            "bounds_4326": bounds,
            "zoom_min": req.zoom_min,
            "zoom_max": req.zoom_max,
            "finished_at": now,
            "provenance": provenance,
            "persisted": persisted,  # v5-audit F1: هل حُفِظ في DB فعلاً (لا الذاكرة فقط)؟
        }
        job["status"] = JobStatus.completed
        job["progress_pct"] = 100
        job["finished_at"] = now
        _jobs.set(job_id, job)  # تثبيت النتيجة المكتملة (Redis/ذاكرة)
        logger.info(f"job {job_id} completed → layer {layer_id} persisted={persisted}")
    except Exception as e:  # noqa: BLE001
        job["status"] = JobStatus.failed
        # لا نُخزّن تفاصيل الاستثناء الخام في job status لأنّها تُقرأ عبر API وقد
        # تحتوي مسارات ملفات/روابط/تفاصيل مكتبات. السجلّ الداخلي يحتفظ بنوع الخطأ،
        # ولـHTTPException يضيف status/detail (نصّنا المتحكَّم به) — النوع وحده جعل
        # فشل backfill غير قابل للتشخيص (بلاغ 2026-07-04: «HTTPException» بلا سبب).
        job["error_message"] = "raster_processing_failed"
        _jobs.set(job_id, job)  # تثبيت الفشل (Redis/ذاكرة)
        _http = f" [{e.status_code}] {e.detail}" if isinstance(e, HTTPException) else ""
        # exc_info=True: السجلّ الداخلي يحمل التتبّع الكامل — الرسالة العامّة كانت «TypeError»
        # عارياً بعد بناء VRT فتعذّر التشخيص (بلاغ لوج المستخدم). الرمز العامّ للعميل يبقى مُعقَّماً.
        logger.error("job %s failed: %s%s", job_id, type(e).__name__, _http, exc_info=True)


def _run_batch_processing(job_id: str, req: BatchProcessRequest):
    """يحسب عدّة مؤشّرات من نفس المشهد في مهمّة واحدة (كفاءة I/O).

    صدق: يعالج كلّ مؤشّر فعليّاً ويسجّل نتيجته. التوفير الحقيقي يأتي من قراءة
    المشهد مرّة (في الإنتاج مع rasterio)؛ بنيويّاً نتتبّع الكلّ في job واحد مع
    عزل فشل كلّ مؤشّر (فشل واحد لا يُسقط الباقي).
    """
    # نطفّر المهمّة محليّاً ونثبّتها في المخزن (Redis/ذاكرة) عند نقاط الانتقال.
    job = _jobs.get(job_id) or {"job_id": job_id}
    job["status"] = JobStatus.processing
    job["started_at"] = datetime.now(UTC).isoformat()
    _jobs.set(job_id, job)
    results = {}
    failed = {}
    total = len(req.indicators)
    for i, ind in enumerate(req.indicators):
        # ابنِ ProcessRequest فرديّاً لكلّ مؤشّر (يعيد استخدام المنطق المُختبَر)
        single = ProcessRequest(
            tenant_id=req.tenant_id,
            field_id=req.field_id,
            raster_url=req.raster_url,
            indicator=ind,
            source_format=req.source_format,
            bands=req.bands,
            clip_polygon_geojson=req.clip_polygon_geojson,
            apply_cloud_mask=req.apply_cloud_mask,
            scene_id=req.scene_id,
            capture_datetime=req.capture_datetime,
            geometry_revision=req.geometry_revision,  # v143: نَسَب الهندسة عبر المؤشّرات
        )
        sub_job_id = f"{job_id}_{ind.value}"
        _jobs.set(
            sub_job_id,
            {
                "job_id": sub_job_id,
                "status": JobStatus.pending,
                "progress_pct": 0,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        try:
            _run_processing(sub_job_id, single)
            sj = _jobs.get(sub_job_id) or {}
            if sj["status"] == JobStatus.completed:
                results[ind.value] = sj.get("layer_id") or sub_job_id
            else:
                failed[ind.value] = sj.get("error_message", "unknown")
        except Exception as e:  # noqa: BLE001 — عزل لكلّ مؤشّر
            # توحيد main↔cert (#542): رمز عامّ للعميل + السجلّ الداخلي يحمل النوع
            # (+ status/detail لـHTTPException — نصّنا المتحكَّم به، لا تسريب نصّ خام).
            _http = f" [{e.status_code}] {e.detail}" if isinstance(e, HTTPException) else ""
            logger.warning("مهمّة فرعيّة %s فشلت: %s%s", ind.value, type(e).__name__, _http)
            failed[ind.value] = "processing_failed"
        job["progress_pct"] = int((i + 1) / total * 100)

    job["status"] = JobStatus.completed if results else JobStatus.failed
    job["finished_at"] = datetime.now(UTC).isoformat()
    job["batch_results"] = results
    job["batch_failed"] = failed
    _jobs.set(job_id, job)  # تثبيت نتيجة الدفعة (Redis/ذاكرة)
    logger.info("batch %s: %d نجح، %d فشل", job_id, len(results), len(failed))


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
# تطبيع أسماء المؤشرات القادمة من الواجهة.
# - salinity يعرض في UI لكنه يحسب داخلياً كـNDSI.
# - ndvu خطأ شائع في الاختيار/الترجمة؛ نعامله كـNDVI بدل 404.
_GRID_INDEX_ALIASES = {
    "salinity": "ndsi",
    "salt": "ndsi",
    "soil_salinity": "ndsi",
    "ndvu": "ndvi",
    "vegetation": "ndvi",
    "moisture": "ndmi",
}


def _normalize_index(index: str | None) -> str:
    key = (index or "ndvi").strip().lower().replace(" ", "_").replace("-", "_")
    return _GRID_INDEX_ALIASES.get(key, key)


def _display_index(index: str | None) -> str:
    key = (index or "ndvi").strip().lower().replace(" ", "_").replace("-", "_")
    if key in ("salinity", "salt", "soil_salinity"):
        return "salinity"
    if key == "ndvu":
        return "ndvi"
    return key


def _find_field_layer(field_id: str, index: str, date: str) -> dict | None:
    """يجد أحدث طبقة (لها COG) لحقل+مؤشّر، اختياريّاً بتاريخ محدّد.

    date="latest" → أحدث طبقة؛ "YYYY-MM-DD" → مطابقة acquisition_date.
    يُرجِع سجلّ الطبقة أو None (لا COG حقيقي متاح).
    """
    layer_ids = _field_layers.get(field_id, [])
    internal = _normalize_index(index)
    cands = []
    for lid in layer_ids:
        lyr = _layers.get(lid)
        if not lyr or not lyr.get("cog_url"):
            continue
        if lyr.get("index") != internal:
            continue
        cands.append(lyr)
    if not cands:
        return None
    if date and date != "latest":
        # طلب تاريخ محدّد يجب أن يكون صارماً: لا نرجع آخر COG عند غياب التاريخ،
        # وإلا تعرض الخريطة/البلاطات صورة تاريخ آخر عند تحريك الـTimeline.
        dated = [c for c in cands if (c.get("acquisition_date") or "").startswith(date)]
        if not dated:
            return None
        cands = dated
    # latest = أحدث acquisition_date فعليّاً، ثم created_at ككاسر تعادل.
    # created_at وحده قد يختار إعادة معالجة قديمة أُنشئت لاحقاً بدل أحدث صورة جوية.
    cands.sort(
        key=lambda c: (str(c.get("acquisition_date") or ""), str(c.get("created_at") or "")),
        reverse=True,
    )
    return cands[0]


def _grid_from_cog(layer: dict, index: str, date: str, grid: int) -> dict | None:
    """يقرأ COG الطبقة، يصغّره grid×grid (block-mean متجاهلاً NaN)، يصنّف
    المناطق، ويبني عقد الشبكة الحقيقي (real_data=True). يُرجِع None عند
    تعذّر القراءة (لا rasterio / ملفّ مفقود / لا شبكة)."""
    try:
        import indicator_grid as ig
        import numpy as np
        import rasterio
        from rasterio.warp import transform_bounds
    except Exception:  # noqa: BLE001 — rasterio غير متوفّر → fallback محاكاة
        return None

    cog_url = layer["cog_url"]
    path = object_store.to_gdal_path(cog_url)
    try:
        with rasterio.open(path) as src:
            arr = src.read(1).astype("float64")
            if src.nodata is not None:
                arr = np.where(arr == src.nodata, np.nan, arr)
            # bbox بـ4326 من حدود الـCOG الأصليّة (UTM غالباً)
            if src.crs is not None:
                bb = list(transform_bounds(src.crs, "EPSG:4326", *src.bounds))
            else:
                bb = list(src.bounds)
    except Exception:  # noqa: BLE001 — قراءة فشلت (مثلاً شبكة /vsicurl محجوبة)
        return None

    part = ig.grid_from_array(arr, index, grid)
    return {
        "field_id": layer.get("field_id") or "",
        "index": index,
        "date": (layer.get("acquisition_date") or date),
        "bbox": [round(float(x), 6) for x in bb],
        "rows": part["rows"],
        "cols": part["cols"],
        "grid": part["grid"],
        "stats": part["stats"],
        "zones": part["zones"],
        "source": layer.get("source_format") or "raster",
        "real_data": True,
        "cloud_pct": layer.get("cloud_pct"),
        # v131 (v62.3-B): إشارات جودة الصور لمستهلكي المصب (VRA/المناطق، v62.3-C).
        "cloud_cover": layer.get("cloud_cover"),
        "valid_pixel_ratio": layer.get("valid_pixel_ratio"),
        "coverage_ratio": layer.get("coverage_ratio"),
        "index_quality_flags": layer.get("index_quality_flags"),
        "confidence": layer.get("confidence"),
        "quality": layer.get("quality"),
    }


async def _rehydrate_field_layer_from_db(field_id: str, internal: str, date: str) -> dict | None:
    """يستعيد طبقة COG من raster_assets ويبنيها في الذاكرة. يُرجِعها أو None.

    معرّف الطبقة **مخصّص بالتاريخ** (`db_{field}_{index}_{acq}`) — كي لا يخلط ترطيبُ
    تاريخ محدّد مع «latest» (إصلاح FINDING-001: كان `db_{field}_{index}` يجعل طلبَ
    latest لاحقاً يُعيد تاريخاً قديماً مُرطَّباً بلا استشارة القاعدة).
    """
    try:
        import time as _t

        import db_persist

        asset = await db_persist.fetch_latest_asset(
            field_id, internal, date, tenant_id=_REQ_TENANT.get()
        )
        if not asset or not asset.get("cog_url"):
            return None
        if not object_store.exists_locally(asset["cog_url"]):
            logger.warning("raster_assets hit but COG missing on host: %s", asset["cog_url"])
            return None
        acq = asset.get("acquisition_date")
        lid = f"db_{field_id}_{internal}_{acq or 'nodate'}"
        _layers[lid] = {
            "cog_url": asset["cog_url"],
            "index": internal,
            # v11-F4: هويّة/نَسَب الطبقة المُعاد ترطيبها — field_id (كان يغيب فتعود شبكة
            # بلا هويّة) + geometry_revision/asset_status/scene_id/processing_job_id كي
            # يُميَّز ready/stale ويُربط run_item→job→asset. (القارئ يُرجِع ready حصراً.)
            "field_id": field_id,
            "tenant_id": _REQ_TENANT.get(),
            "acquisition_date": acq,
            "bounds_4326": asset.get("bounds_4326"),
            "cloud_pct": asset.get("cloud_pct"),
            "cloud_cover": asset.get("cloud_cover"),
            "valid_pixel_ratio": asset.get("valid_pixel_ratio"),
            "coverage_ratio": asset.get("coverage_ratio"),
            "index_quality_flags": asset.get("index_quality_flags"),
            "confidence": asset.get("confidence"),
            "quality": asset.get("quality"),
            "cloud_mask_applied": asset.get("cloud_mask_applied"),
            "scene_id": asset.get("scene_id"),
            "geometry_revision": asset.get("geometry_revision"),
            "asset_status": asset.get("asset_status"),
            "processing_job_id": asset.get("processing_job_id"),
            "created_at": acq or _t.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _field_layers.setdefault(field_id, [])
        if lid not in _field_layers[field_id]:
            _field_layers[field_id].append(lid)
        return _layers[lid]
    except Exception as e:  # noqa: BLE001 — غياب القاعدة لا يُفشل القراءة
        logger.warning("DB rehydrate skipped (%s): %s", field_id, e)
        return None


async def _resolve_field_layer(field_id: str, index: str, date: str) -> dict | None:
    """يجد طبقة COG للحقل: من الذاكرة أوّلاً، وإلّا يُعيد الترطيب من raster_assets.

    FINDING-001: طلب «latest» لا يثق بذاكرة قد تحوي ترطيبَ تاريخ محدّد أقدم فقط —
    يستشير القاعدة عن الأحدث ويختار الأحدث acquisition_date بين الذاكرة والقاعدة.
    طلب تاريخ محدّد يبقى ذاكرةً-أوّلاً (صارم بالتاريخ في _find_field_layer).
    """
    internal = _normalize_index(index)
    mem = _find_field_layer(field_id, index, date)

    if date and date != "latest":
        if mem is not None:
            return mem
        return await _rehydrate_field_layer_from_db(field_id, internal, date)

    # date == "latest": الذاكرة قد تكون قديمة (ترطيب تاريخ محدّد سابق) — استشِر القاعدة.
    db_layer = await _rehydrate_field_layer_from_db(field_id, internal, "latest")
    if db_layer is None:
        return mem  # لا قاعدة/لا أصل ⇒ أفضل ما في الذاكرة (best-effort)
    if mem is None:
        return db_layer
    # اختر الأحدث acquisition_date فعليّاً (الذاكرة قد تحمل معالجةً حيّةً أحدث من القاعدة).
    mem_d = str(mem.get("acquisition_date") or "")
    db_d = str(db_layer.get("acquisition_date") or "")
    return mem if mem_d >= db_d else db_layer


async def _rvi_from_sar_cog(field_id: str, date: str) -> float | None:
    """RVI من COG رادار ثنائي النطاق (VV=band1, VH=band2) إن وُجد، وإلّا None.

    صدق: يحتاج COG Sentinel-1 مُعالَجاً (نطاقَين) للحقل؛ لا اختراع عند غيابه.
    """
    layer = await _resolve_field_layer(field_id, "rvi", date)
    if layer is None:
        layer = await _resolve_field_layer(field_id, "sar", date)
    if layer is None:
        return None
    try:
        import numpy as np
        import rasterio
        import sar_rvi
    except Exception:  # noqa: BLE001 — rasterio غير متوفّر → لا RVI
        return None
    path = object_store.to_gdal_path(layer["cog_url"])
    try:
        with rasterio.open(path) as src:
            if src.count < 2:
                return None  # ليس ثنائي الاستقطاب (VV/VH)
            vv = src.read(1).astype("float64")
            vh = src.read(2).astype("float64")
            if src.nodata is not None:
                vv = np.where(vv == src.nodata, np.nan, vv)
                vh = np.where(vh == src.nodata, np.nan, vh)
    except Exception:  # noqa: BLE001 — قراءة فشلت → لا RVI
        return None
    res = sar_rvi.compute_rvi(vv, vh, in_db=False)
    return res["rvi_mean"] if res["valid_pixels"] else None


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
    """شبكة المؤشّر الحقيقيّة (من COG) لحقل+مؤشّر+تاريخ، أو None إن لم تتوفّر.

    صدق: لا COG / لا rasterio / لا شبكة ⇒ None (لا محاكاة هنا — كشف التغيّر يجب
    أن يبني على بيانات حقيقيّة فقط، لا يُفبرَك تغيّر من شبكتين مُولَّدتين).
    """
    layer = await _resolve_field_layer(field_id, index, date)
    if layer is None:
        return None
    return _grid_from_cog(layer, index, date, grid)


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
# (_run_cdse_processing/ProcessCdseRequest/_jobs/…) عدا ٣ مساعِدات للكاش/القفل.
# نضيفها ثمّ نُضمّن راوتر cdse_tiles (يستورد main لاحقاً — بلا دور دائريّ لأنّ
# التضمين في نهاية الملفّ بعد تعريف كلّ الرموز، كنمط register_routers).
_cdse_tile_cache: dict[str, tuple[float, str]] = {}
_cdse_cache_lock: object | None = None  # asyncio.Lock — تُنشأ عند أوّل استخدام
_cdse_key_locks: dict[str, object] = {}  # per-cache-key asyncio.Lock (single-flight)


def _cdse_lock():
    """يُرجع asyncio.Lock الوحيد لحماية _cdse_tile_cache + سجلّ أقفال المفاتيح (lazy).

    قفل **قصير**: يُحمَل فقط أثناء قراءة/كتابة الكاش وإنشاء قفل المفتاح — لا يُحمَل أبداً
    أثناء جلب CDSE الشبكيّ (ذاك تحت قفل المفتاح). هكذا لا يحجب جلبٌ بطيء/فاشل لحقلٍ
    بلاطاتِ كلّ الحقول الأخرى (كان قفلاً عالميّاً حول الجلب+الإعادة ⇒ توقّف على مستوى الخريطة).
    """
    global _cdse_cache_lock
    import asyncio

    if _cdse_cache_lock is None:
        _cdse_cache_lock = asyncio.Lock()
    return _cdse_cache_lock


def _cdse_key_lock(cache_key: str):
    """قفل single-flight لكلّ مفتاح كاش (يجب النداء تحت ``_cdse_lock()``).

    بلاطات نفس (حقل/مؤشّر/تاريخ/هندسة) تتشارك قفلاً واحداً ⇒ جلب CDSE مرّة واحدة
    (يحمي حصّة المزوّد)، بينما حقول/تواريخ مختلفة تتقدّم بالتوازي بلا حجب متبادل."""
    import asyncio

    lock = _cdse_key_locks.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        _cdse_key_locks[cache_key] = lock
    return lock


def _cdse_prune_key_locks_locked() -> None:
    """يُزيل أقفال المفاتيح التي لا كاش حيّ لها (يجب النداء تحت ``_cdse_lock()``).

    يمنع نموّ ``_cdse_key_locks`` بلا حدّ عند تصفّح حقول/تواريخ كثيرة: نُبقي فقط أقفال
    المفاتيح التي ما زال لها صفّ في ``_cdse_tile_cache``."""
    live = set(_cdse_tile_cache.keys())
    for key in list(_cdse_key_locks.keys()):
        if key not in live:
            _cdse_key_locks.pop(key, None)


def _bbox_from_geom(geom: dict | None) -> list[float] | None:
    """يحسب [west, south, east, north] من هندسة GeoJSON (Polygon/MultiPolygon/Feature)."""
    if not geom:
        return None
    try:
        gtype = geom.get("type", "")
        if gtype == "Feature":
            geom = geom.get("geometry") or {}
            gtype = geom.get("type", "")
        coords: list = []
        if gtype == "Polygon":
            coords = geom.get("coordinates", [[]])[0]
        elif gtype == "MultiPolygon":
            for ring in geom.get("coordinates", []):
                coords.extend(ring[0] if ring else [])
        if not coords:
            return None
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return [min(lons), min(lats), max(lons), max(lats)]
    except Exception:  # noqa: BLE001
        return None


# ════════════════════════════════════════════════════════════════════
# تسجيل تلقائيّ لكلّ راوترات routers/ (تفكيك main.py محفوظ السلوك). يُستدعى في
# نهاية الملفّ بعد تعريف app وكلّ التبعيّات المشتركة (مساعِدات/نماذج/حالة/مساعِدات
# CDSE) فيُحلّ الاستيراد الدائريّ — وحدات routers تستورد رموزاً من main عبر main.X.
# يضمّ register_routers أيضاً routers/cdse_tiles.py تلقائيّاً (لا تضمين يدويّ).
from router_registry import register_routers  # noqa: E402

register_routers(app)
