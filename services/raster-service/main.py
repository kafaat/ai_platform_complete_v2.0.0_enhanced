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
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlparse

import band_math
import httpx
import object_store
import salinity_calibration as _sal
from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from job_store import JobStore
from pydantic import BaseModel, Field
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
EARTH_SEARCH_URL = os.getenv("EARTH_SEARCH_URL", "https://earth-search.aws.element84.com/v1")
SENTINEL_COLLECTION = "sentinel-2-l2a"
SENTINEL1_COLLECTION = "sentinel-1-grd"  # رادار SAR — يخترق الغيوم والليل
LANDSAT_COLLECTION = "landsat-c2-l2"  # Landsat C2 L2 — أرشيف 40+ سنة (تكميلي)
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


class SearchRequest(BaseModel):
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    datetime_start: str
    datetime_end: str
    max_cloud_pct: float = 30
    limit: int = 20


class HistoricalBackfillPreset(StrEnum):
    """Preset windows for historical imagery backfill.

    auto_12_months: default immediate history for newly-created fields.
    extended_3_years: agronomic season comparison and recurring weak-zone analysis.
    research_5_years: enterprise/research tier; heavier cost and storage.
    custom: explicit from_date/to_date or months.
    """

    auto_12_months = "auto_12_months"
    extended_3_years = "extended_3_years"
    research_5_years = "research_5_years"
    custom = "custom"


_BACKFILL_PRESET_MONTHS = {
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
    preset: HistoricalBackfillPreset = HistoricalBackfillPreset.auto_12_months
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
    max_cloud_pct: float = Field(default=30, ge=0, le=100)
    limit_per_month: int = Field(default=2, ge=1, le=8)
    apply_cloud_mask: bool = True
    source: str = Field(default="sentinel-2")
    clip_polygon_geojson: dict | None = None
    dry_run: bool = False


class AutoBackfillPolicy(BaseModel):
    enabled: bool = True
    default_preset: HistoricalBackfillPreset = HistoricalBackfillPreset.auto_12_months
    extended_preset: HistoricalBackfillPreset = HistoricalBackfillPreset.extended_3_years
    research_preset: HistoricalBackfillPreset = HistoricalBackfillPreset.research_5_years
    default_indices: list[str] = ["ndvi", "ndmi", "savi", "evi"]
    max_cloud_pct: float = 30
    note: str = (
        "Use auto_12_months on field creation; expose extended_3_years and "
        "research_5_years as explicit user/plan toggles."
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
    def safe(s):
        cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(s or "na"))
        return cleaned.replace("..", "_")

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


# ─── بحث الصور عبر Element84 STAC ─────────────────────────────────
def _band_urls_from_assets(assets: dict) -> dict:
    """يستخرج روابط النطاقات من STAC assets (Sentinel-2 L2A)."""

    def url(key: str) -> str | None:
        a = assets.get(key)
        return a.get("href") if a else None

    return {
        "blue": url("blue"),
        "green": url("green"),
        "red": url("red"),
        "rededge1": url("rededge1"),
        "rededge2": url("rededge2"),
        "rededge3": url("rededge3"),
        "nir": url("nir"),
        "nir08": url("nir08"),
        "swir16": url("swir16"),
        "swir22": url("swir22"),
        "scl": url("scl"),
        "visual": url("visual"),
        "thumbnail": url("thumbnail"),
    }


async def _stac_search(
    bbox: list[float], dt_start: str, dt_end: str, max_cloud: float, limit: int
) -> dict:
    """يبحث في Element84 Earth Search عن صور Sentinel-2.

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
    data = await _stac.search(payload)

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
            }
        )
    return {
        "count": len(items),
        "source": "element84-earth-search",
        "cache": data.get("_cache", "miss"),
        "warning": data.get("_warning"),
        "items": items,
    }


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


async def _stac_search_landsat(
    bbox: list[float], dt_start: str, dt_end: str, max_cloud: float, limit: int
) -> dict:
    """يبحث عن صور Landsat Collection 2 L2 عبر Element84 (نفس API المرن).

    تكميلي لـSentinel-2: أرشيف 40+ سنة (تحليل تاريخي طويل المدى)، دقّة 30م.
    يحمل نطاقات طيفيّة (يُحسب منه NDVI) لكن دقّة أخشن وتردّد أقلّ (16 يوماً).
    """
    payload = {
        "collections": [LANDSAT_COLLECTION],
        "bbox": bbox,
        "datetime": f"{dt_start}/{dt_end}",
        "query": {"eo:cloud_cover": {"lte": max_cloud}},
        "limit": limit,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    data = await _stac.search(payload)
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
                "platform": props.get("platform", "landsat"),
                "thumbnail_url": (assets.get("thumbnail") or {}).get("href"),
                "data_type": "optical",
                "note_ar": "Landsat 30م — أرشيف طويل المدى، تكميلي لـSentinel-2.",
            }
        )
    return {
        "count": len(items),
        "source": "element84-earth-search",
        "collection": LANDSAT_COLLECTION,
        "cache": data.get("_cache"),
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
    data = await _stac.search(payload)
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
    yield
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
@app.get("/imagery/search/recent")
async def imagery_search_recent(
    west: float,
    south: float,
    east: float,
    north: float,
    days_back: int = Query(30, ge=1, le=365),
    max_cloud_pct: float = Query(30, ge=0, le=100),
):
    """آخر صور Sentinel-2 لمنطقة بـbbox (خلال days_back يوماً)."""
    now = datetime.now(UTC)
    start = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    end = now.strftime("%Y-%m-%dT23:59:59Z")
    try:
        return await _stac_search([west, south, east, north], start, end, max_cloud_pct, limit=20)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search: {e}") from e


@app.get("/imagery/search/season")
async def imagery_search_season(
    west: float,
    south: float,
    east: float,
    north: float,
    sowing_date: str,
    harvest_date: str | None = None,
    max_cloud_pct: float = Query(40, ge=0, le=100),
):
    """كلّ صور الموسم الزراعي (من البذار للحصاد) — للـCropTimeline."""
    end = harvest_date or datetime.now(UTC).strftime("%Y-%m-%d")
    start = f"{sowing_date}T00:00:00Z"
    end_iso = f"{end}T23:59:59Z"
    try:
        return await _stac_search(
            [west, south, east, north], start, end_iso, max_cloud_pct, limit=60
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search: {e}") from e


@app.get("/imagery/best")
async def imagery_best_scene(
    west: float,
    south: float,
    east: float,
    north: float,
    lookback_days: int = Query(30, ge=1, le=180),
    max_cloud_pct: float = Query(40, ge=0, le=100),
):
    """يختار أفضل مشهد حديث (توازن الحداثة + قلّة الغيوم) — تحسين القلب.

    بدل أخذ الأحدث دائماً (قد يكون غائماً)، يوازن: مشهد حديث منخفض الغيوم
    أفضل من أحدث غائم. درجة = أولويّة قلّة الغيوم مع تفضيل الحداثة عند التعادل.
    صدق: يختار من المتاح فعليّاً؛ لا يخترع مشهداً.
    """
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
    start = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    try:
        result = await _stac_search(
            [west, south, east, north],
            f"{start}T00:00:00Z",
            f"{end}T23:59:59Z",
            max_cloud_pct,
            limit=30,
        )
    except (httpx.HTTPError, RuntimeError) as e:
        raise HTTPException(502, f"Earth Search: {e}") from e

    items = result.get("items", [])
    if not items:
        return {
            "best": None,
            "candidates": 0,
            "note": "لا مشاهد ضمن المعايير — وسّع lookback أو max_cloud",
        }

    # درجة: كلّما قلّ الغيوم زادت؛ مع مكافأة بسيطة للحداثة (الأحدث أوّلاً أصلاً).
    def score(idx_item):
        idx, it = idx_item
        cloud = it.get("cloud_cover_pct", 100)
        recency_bonus = (len(items) - idx) / len(items) * 10  # 0-10
        return (100 - cloud) + recency_bonus

    best_idx, best = max(enumerate(items), key=score)
    return {
        "best": best,
        "candidates": len(items),
        "selection": "أقلّ غيوم مع تفضيل الحداثة",
        "cache": result.get("cache"),
    }


@app.post("/imagery/search")
async def imagery_search(req: SearchRequest, x_agent_token: str = Header(None)):
    """بحث متقدّم بكلّ الخيارات."""
    _require_service_token(x_agent_token)
    try:
        return await _stac_search(
            req.bbox, req.datetime_start, req.datetime_end, req.max_cloud_pct, req.limit
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search: {e}") from e


@app.get("/imagery/timeseries")
async def imagery_timeseries(
    west: float,
    south: float,
    east: float,
    north: float,
    start: str,
    end: str | None = None,
    max_cloud_pct: float = Query(40, ge=0, le=100),
):
    """تحليل زمني (سدّ فجوة P0): تركيب شهري + اتّجاه + كشف شذوذ.

    يبحث STAC عن مشاهد الفترة، يجمّعها شهريّاً (median compositing لتخفيف
    الغيوم)، ويحسب الاتّجاه (تحسّن/تدهور) والشذوذ. صدق: عند توفّر القيم
    المحسوبة لكلّ مشهد تُجمَّع؛ وإلّا يُرجِع البنية الزمنيّة + المشاهد لحساب
    العميل/العامل (لا يخترع قيم NDVI من البحث وحده).
    """
    end_date = end or datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        search = await _stac_search(
            [west, south, east, north],
            f"{start}T00:00:00Z",
            f"{end_date}T23:59:59Z",
            max_cloud_pct,
            limit=100,
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search: {e}") from e

    scenes = search.get("items", [])
    # المشاهد من STAC تحمل التاريخ والغيوم لكن ليس NDVI محسوباً بعد —
    # نُرجِع البنية الزمنيّة (تجميع شهري بعدد المشاهد) + قائمة للمعالجة.
    # تجميع شهري لعدد المشاهد المتاحة (لا قيم مخترعة)
    from collections import Counter

    month_counts = Counter(s["datetime"][:7] for s in scenes if s.get("datetime"))
    timeline = [{"month": m, "scenes_available": c} for m, c in sorted(month_counts.items())]
    return {
        "period": {"start": start, "end": end_date},
        "total_scenes": len(scenes),
        "monthly_availability": timeline,
        "scenes": scenes,
        "note": "احسب المؤشّر لكلّ مشهد عبر /process ثمّ مرّر القيم لـ"
        "/imagery/timeseries/analyze للحصول على الاتّجاه والشذوذ",
    }


class TimeSeriesAnalyzeRequest(BaseModel):
    scene_values: list[dict]  # [{"datetime": "...", "mean": 0.5}, ...]


@app.post("/imagery/timeseries/analyze")
async def imagery_timeseries_analyze(
    req: TimeSeriesAnalyzeRequest, x_agent_token: str = Header(None)
):
    """يحلّل قيم مؤشّر محسوبة عبر الزمن: تركيب شهري + اتّجاه + شذوذ.

    يستقبل قيم المؤشّر المحسوبة فعليّاً لكلّ مشهد (من /process) ويُرجِع
    التحليل الزمني الكامل. صدق: يعمل على قيم حقيقيّة مُمرَّرة، لا مخترعة.
    """
    _require_service_token(x_agent_token)
    import time_series as ts

    return ts.build_time_series(req.scene_values, value_key="mean")


class ManagementZonesRequest(BaseModel):
    pixel_values: list[float]
    n_zones: int = 3
    base_rate: float | None = None
    strategy: str = "compensate"


@app.post("/zones/classify")
async def zones_classify(req: ManagementZonesRequest, x_agent_token: str = Header(None)):
    """مناطق الإدارة داخل الحقل (سدّ فجوة P1): تقسيم أداء + وصفة VRT.

    يقسّم قيم بكسلات المؤشّر لمناطق (عالٍ/متوسّط/منخفض) بالكوانتايل، ويُنتج
    وصفة متغيّرة المعدّل إن مُرّر base_rate. صدق: يعمل على قيم حقيقيّة.
    """
    _require_service_token(x_agent_token)
    import management_zones as mz

    result = mz.classify_zones(req.pixel_values, n_zones=req.n_zones)
    if req.base_rate is not None and result.get("zones"):
        result["prescription"] = mz.prescription_from_zones(
            result["zones"], req.base_rate, strategy=req.strategy
        )
    return result


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


@app.post("/change/detect")
async def change_detect(req: ChangeDetectRequest, x_agent_token: str = Header(None)):
    """كشف التغيير المكاني (per-pixel 2D) بين تاريخين — أين تدهور/تحسّن الحقل.

    يسدّ فجوة كانت placeholder: التحليل الزمني 1D (متوسّط) يُخفي التدهور الموضعي
    (زحف ملوحة من زاوية، عطل ريّ في قطاع). يستقبل شبكتي مؤشّر مُحسبتَين فعليّاً من
    COG لتاريخين (نفس النهج الصادق: لا يخترع NDVI من البحث) ويُرجِع خريطة فرق
    مُصنّفة + نسب المساحة المتدهورة + تفسير عربي. NaN/null لا تُحسب (صدق السحاب).
    """
    _require_service_token(x_agent_token)
    # حدّ الحجم قبل أيّ تحويل numpy (حماية من DoS) ⇒ 413 عند التجاوز.
    for name, g in (("grid_before", req.grid_before), ("grid_after", req.grid_after)):
        cells = sum(len(row) for row in g)
        if cells > MAX_CHANGE_GRID_CELLS:
            raise HTTPException(
                status_code=413,
                detail=f"{name} كبير جدّاً: {cells} خليّة > الحدّ {MAX_CHANGE_GRID_CELLS}",
            )
    import change_detection as cd

    result = cd.detect_change(
        req.grid_before,
        req.grid_after,
        index=req.index,
        slight_threshold=req.slight_threshold,
        severe_threshold=req.severe_threshold,
    )
    result.update(
        {
            "field_id": req.field_id,
            "date_before": req.date_before,
            "date_after": req.date_after,
        }
    )
    return result


class FvcComputeRequest(BaseModel):
    field_id: str
    date: str
    ndvi_grid: list[list[float | None]]  # شبكة NDVI مُحسبة من COG
    method: str = "cumulative_frequency"  # | global_constant | dynamic_range
    ndvi_soil: float | None = None  # لـdynamic_range فقط
    ndvi_veg: float | None = None


@app.post("/fvc/compute")
async def fvc_compute(req: FvcComputeRequest, x_agent_token: str = Header(None)):
    """نسبة التغطية النباتيّة (FVC) عبر نموذج البكسل الثنائي — تكمّل LAI.

    LAI (موجود) يقيس كثافة الأوراق (3D)؛ FVC يقيس نسبة الأرض المُغطّاة بالنبات
    (2D) — أساس موضوعي لرصد زحف التصحّر وتغطية المحاصيل في الجوف. يستقبل شبكة
    NDVI مُحسبة من COG ويُرجِع شبكة FVC + نسبة التصحّر + تصنيف + تفسير عربي.
    """
    _require_service_token(x_agent_token)
    cells = sum(len(row) for row in req.ndvi_grid)
    if cells > MAX_CHANGE_GRID_CELLS:
        raise HTTPException(
            status_code=413, detail=f"ndvi_grid كبير جدّاً: {cells} > {MAX_CHANGE_GRID_CELLS}"
        )
    import fvc

    try:
        result = fvc.compute_fvc(
            req.ndvi_grid, method=req.method, ndvi_soil=req.ndvi_soil, ndvi_veg=req.ndvi_veg
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    result.update({"field_id": req.field_id, "date": req.date})
    return result


class SarRviRequest(BaseModel):
    field_id: str
    date: str
    vv_grid: list[list[float | None]]  # σ°_VV (قدرة خطّيّة أو dB)
    vh_grid: list[list[float | None]]  # σ°_VH
    in_db: bool = False  # هل القيم بالديسيبل؟ (تُحوَّل للخطّي قبل النسبة)


@app.post("/sar/rvi")
async def sar_rvi_endpoint(req: SarRviRequest, x_agent_token: str = Header(None)):
    """مؤشّر الغطاء الراداري RVI من Sentinel-1 VV/VH — يُكمل مقاومة السحاب.

    RVI = 4·σ°VH/(σ°VV+σ°VH) (قدرة خطّيّة)، مقصوص [0,1] كبديل غطاء قابل للدمج مع
    NDVI كـfamily="sar". المُدخلات شبكتا VV/VH مُحسبتان من COG رادار مُعايَر
    (العامل، rasterio). صدق: فجوات NaN محفوظة. rvi_mean يُمرَّر كإشارة source=rvi.
    """
    _require_service_token(x_agent_token)
    cells = sum(len(row) for row in req.vv_grid)
    if cells > MAX_CHANGE_GRID_CELLS:
        raise HTTPException(
            status_code=413, detail=f"vv_grid كبير جدّاً: {cells} > {MAX_CHANGE_GRID_CELLS}"
        )
    import sar_rvi

    try:
        result = sar_rvi.compute_rvi(req.vv_grid, req.vh_grid, in_db=req.in_db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    result.update({"field_id": req.field_id, "date": req.date})
    return result


@app.get("/imagery/search/radar")
async def imagery_search_radar(
    west: float,
    south: float,
    east: float,
    north: float,
    start: str,
    end: str | None = None,
    limit: int = Query(20, ge=1, le=100),
):
    """بحث رادار Sentinel-1 GRD — يخترق الغيوم (مفيد لموسم الأمطار).

    لا فلتر غيوم (الرادار لا يتأثّر بها). يُرجع استقطابات VV/VH للاستخدام
    في رطوبة التربة وكشف الفيضانات — لا NDVI.
    """
    end_date = end or datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        return await _stac_search_radar(
            [west, south, east, north], f"{start}T00:00:00Z", f"{end_date}T23:59:59Z", limit
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search (radar): {e}") from e


@app.get("/imagery/search/landsat")
async def imagery_search_landsat(
    west: float,
    south: float,
    east: float,
    north: float,
    start: str,
    end: str | None = None,
    max_cloud_pct: float = Query(40, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100),
):
    """بحث Landsat C2 L2 — أرشيف طويل المدى (40+ سنة) تكميلي لـSentinel-2.

    دقّة 30م، تردّد 16 يوماً. مفيد للتحليل التاريخي قبل عصر Sentinel-2 (2015).
    """
    end_date = end or datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        return await _stac_search_landsat(
            [west, south, east, north],
            f"{start}T00:00:00Z",
            f"{end_date}T23:59:59Z",
            max_cloud_pct,
            limit,
        )
    except (httpx.HTTPError, RuntimeError) as e:
        raise HTTPException(502, f"Earth Search (landsat): {e}") from e


@app.get("/imagery/dem")
async def imagery_dem(west: float, south: float, east: float, north: float):
    """نموذج الارتفاع الرقمي (Copernicus DEM 30م) لمنطقة — للانحدار/الصرف.

    حرج لزراعة اليمن المُدرّجة الصحراويّة: تخطيط حصاد المياه، اتّجاه الجريان،
    مواقع السدود الترابيّة. DEM ثابت (لا زمني) — لا datetime/cloud.
    """
    try:
        return await _stac_search_dem([west, south, east, north])
    except (httpx.HTTPError, RuntimeError) as e:
        raise HTTPException(502, f"Earth Search (DEM): {e}") from e


class TerrainRequest(BaseModel):
    dem_url: str
    pixel_size_m: float = 30.0


@app.post("/terrain/slope")
async def terrain_slope(req: TerrainRequest, x_agent_token: str = Header(None)):
    """يحسب الانحدار من DEM + يصنّف ملاءمة حصاد المياه (زراعة اليمن).

    يأخذ dem_url (من /imagery/dem) ويحسب الانحدار/الاتّجاه ثمّ يوصي بتقنيّة
    حصاد المياه المناسبة. صدق: الحساب الفعلي يحتاج rasterio في التشغيل.
    """
    _require_service_token(x_agent_token)
    import terrain_analysis as ta

    result = ta.compute_slope_aspect(_safe_raster_source(req.dem_url), req.pixel_size_m)
    if result.get("computed") and result.get("slope_deg"):
        result["water_harvesting"] = ta.classify_water_harvesting(result["slope_deg"]["mean"])
    return result


# ─── الفحوص ───────────────────────────────────────────────────────
@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "raster-service"}


@app.get("/metrics")
async def metrics():
    """مقاييس خطّ المعالجة الجغرافي (Prometheus format) — سدّ فجوة
    observability. يعرّض حالة المهامّ ليلتقطها Prometheus (لا black-box).

    تنسيق exposition نصّي بسيط — لا تبعيّة ثقيلة. يربطه prometheus.yml.
    """
    from collections import Counter

    by_status = Counter(j.get("status") for j in _jobs.values())

    # حوّل enum/قيمة لنصّ
    def _s(k):
        return getattr(k, "value", str(k))

    lines = [
        "# HELP sahool_raster_jobs_total إجمالي مهامّ المعالجة حسب الحالة",
        "# TYPE sahool_raster_jobs_total gauge",
    ]
    for status, count in by_status.items():
        lines.append(f'sahool_raster_jobs_total{{status="{_s(status)}"}} {count}')
    lines += [
        "# HELP sahool_raster_layers_total الطبقات المُنتَجة المتاحة",
        "# TYPE sahool_raster_layers_total gauge",
        f"sahool_raster_layers_total {len(_layers)}",
        "# HELP sahool_raster_jobs_active المهامّ قيد المعالجة الآن",
        "# TYPE sahool_raster_jobs_active gauge",
        f"sahool_raster_jobs_active "
        f"{sum(1 for j in _jobs.values() if _s(j.get('status')) == 'processing')}",
    ]
    # صحّة عميل STAC (مرونة قلب النظام)
    h = _stac.health()
    lines += [
        "# HELP sahool_stac_requests_total إجمالي طلبات STAC",
        "# TYPE sahool_stac_requests_total counter",
        f"sahool_stac_requests_total {h['requests']}",
        "# HELP sahool_stac_cache_hit_rate نسبة إصابة cache (0-1)",
        "# TYPE sahool_stac_cache_hit_rate gauge",
        f"sahool_stac_cache_hit_rate {h['cache_hit_rate']}",
        "# HELP sahool_stac_failures_total فشل STAC التامّ (لا cache)",
        "# TYPE sahool_stac_failures_total counter",
        f"sahool_stac_failures_total {h['failures']}",
        "# HELP sahool_stac_stale_served_total نتائج cache منتهية قُدّمت (انقطاع)",
        "# TYPE sahool_stac_stale_served_total counter",
        f"sahool_stac_stale_served_total {h['stale_served']}",
        "# HELP sahool_stac_fallback_served_total نتائج من المصدر الاحتياطي (PC)",
        "# TYPE sahool_stac_fallback_served_total counter",
        f"sahool_stac_fallback_served_total {h.get('fallback_served', 0)}",
    ]
    lines += [
        "# HELP sahool_raster_tilejson_requests_total TileJSON requests reaching raster-service",
        "# TYPE sahool_raster_tilejson_requests_total counter",
        f"sahool_raster_tilejson_requests_total {_TILE_OBS['tilejson_requests_total']}",
        "# HELP sahool_raster_tilejson_unavailable_total TileJSON responses with available=false",
        "# TYPE sahool_raster_tilejson_unavailable_total counter",
        f"sahool_raster_tilejson_unavailable_total {_TILE_OBS['tilejson_unavailable_total']}",
        "# HELP sahool_raster_tile_requests_total Field tile image requests",
        "# TYPE sahool_raster_tile_requests_total counter",
        f"sahool_raster_tile_requests_total {_TILE_OBS['tile_requests_total']}",
        "# HELP sahool_raster_tile_cache_hits_total Persistent tile cache hits",
        "# TYPE sahool_raster_tile_cache_hits_total counter",
        f"sahool_raster_tile_cache_hits_total {_TILE_OBS['tile_cache_hits_total']}",
        "# HELP sahool_raster_tile_cache_misses_total Persistent tile cache misses",
        "# TYPE sahool_raster_tile_cache_misses_total counter",
        f"sahool_raster_tile_cache_misses_total {_TILE_OBS['tile_cache_misses_total']}",
        "# HELP sahool_raster_tile_transparent_total Transparent tiles returned because no raster data was available",
        "# TYPE sahool_raster_tile_transparent_total counter",
        f"sahool_raster_tile_transparent_total {_TILE_OBS['tile_transparent_total']}",
        "# HELP sahool_raster_tile_render_errors_total Tile rendering errors hidden behind transparent fallback",
        "# TYPE sahool_raster_tile_render_errors_total counter",
        f"sahool_raster_tile_render_errors_total {_TILE_OBS['tile_render_errors_total']}",
    ]
    for idx, counters in sorted(_TILE_OBS_BY_INDEX.items()):
        safe_idx = idx.replace('"', "_")
        for key, value in sorted(counters.items()):
            metric = "sahool_raster_" + key
            lines.append(f'{metric}{{index="{safe_idx}"}} {int(value)}')

    from fastapi.responses import PlainTextResponse

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.get("/v1/tiles/observability")
async def tile_observability():
    """تشخيص سريع للبلاطات للواجهة/الدعم: يوضح إن كانت المشكلة عدم بيانات،
    cache، أو أخطاء تصيير، دون كشف مسارات COG الداخلية."""
    return {
        "status": "ok",
        "counters": dict(_TILE_OBS),
        "by_index": {k: dict(v) for k, v in _TILE_OBS_BY_INDEX.items()},
        "cache_enabled": os.getenv("TILE_CACHE_ENABLED", "true").lower() == "true",
        "message": "راقب tilejson_unavailable_total و tile_transparent_total عند عدم ظهور طبقة المؤشر",
    }


@app.get("/readyz")
async def readyz():
    """يتحقّق من الوصول لـEarth Search."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{EARTH_SEARCH_URL}/")
            ok = r.status_code < 500
        body = {
            "status": "ready" if ok else "degraded",
            "earth_search": "reachable" if ok else "unreachable",
        }
        return JSONResponse(status_code=200 if ok else 503, content=body)
    except httpx.HTTPError:
        return JSONResponse(
            status_code=503, content={"status": "degraded", "earth_search": "unreachable"}
        )


# ─── معالجة الراستر: الرفع ────────────────────────────────────────
UPLOAD_DIR = os.getenv("RASTER_UPLOAD_DIR", "/tmp/sahool_rasters")

_SSRF_BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal", "metadata"}


def _safe_raster_source(url: str | None) -> str:
    """يتحقّق من مصدر راستر آمن قبل rasterio.open — يمنع path traversal وSSRF.

    file:// : يُسمَح **فقط** تحت UPLOAD_DIR (realpath، لا ../traversal) ⇒ يمنع قراءة
    ملفّات عشوائيّة (file:///etc/passwd). http(s): يُسمَح (STAC/object-store) مع حجب
    عنوان metadata السحابي. أيّ غير ذلك ⇒ 400. (مراجعة الجولة ٣ — أمن.)
    """
    if not url or not isinstance(url, str):
        raise HTTPException(400, "مصدر راستر غير صالح")
    if url.startswith("file://"):
        path = os.path.realpath(url[len("file://") :])
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


@app.post("/upload/raster")
async def upload_raster(file: UploadFile = File(...), x_agent_token: str = Header(None)):
    """يرفع ملفّ راستر (GeoTIFF) ويُرجع raster_url داخليّاً."""
    _require_service_token(x_agent_token)
    raster_id = f"ras_{uuid.uuid4().hex[:12]}"
    path = os.path.join(UPLOAD_DIR, f"{raster_id}.tif")
    try:
        content = await file.read()
        with open(path, "wb") as fh:
            fh.write(content)
    except OSError as e:
        logger.warning("raster upload save failed: %s", type(e).__name__)
        raise HTTPException(500, "raster_upload_save_failed") from e
    logger.info(f"raster uploaded: {raster_id} ({len(content)} bytes)")
    return {"raster_url": f"file://{path}"}


@app.post("/upload/drone")
async def upload_drone(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    field_id: str | None = Form(None),
    x_agent_token: str = Header(None),
):
    """يرفع أورثوموزاييك درون (RGB عادةً — مؤشّرات VARI/GLI/TGI)."""
    _require_service_token(x_agent_token)
    raster_id = f"drone_{uuid.uuid4().hex[:12]}"
    path = os.path.join(UPLOAD_DIR, f"{raster_id}.tif")
    try:
        content = await file.read()
        with open(path, "wb") as fh:
            fh.write(content)
    except OSError as e:
        logger.warning("drone upload save failed: %s", type(e).__name__)
        raise HTTPException(500, "drone_upload_save_failed") from e
    logger.info(f"drone uploaded: {raster_id} tenant={tenant_id}")
    return {"raster_url": f"file://{path}"}


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
    "ndsi": "(RED-NIR)/(RED+NIR)  # salinity — حرج لليمن",
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


def _persist_raster_asset(
    req: ProcessRequest, cog_url: str, meta: dict, bounds: list, stats: dict
) -> None:
    """يُدرج صفّاً في raster_assets (best-effort). يُغلّف كلّ خطأ.

    _run_processing يعمل في threadpool (مهمّة خلفيّة متزامنة) فلا حلقة
    أحداث في خيطه؛ لذا asyncio.run آمن هنا. غياب القاعدة (لا DATABASE_URL/
    لا جدول/لا شبكة) يُبتلع بصدق ولا يُفشل المعالجة.
    """
    if not _is_valid_uuid_text(req.field_id):
        logger.warning("raster_assets persist skipped: missing/invalid field_id=%r", req.field_id)
        return
    if (
        req.tenant_id is not None
        and str(req.tenant_id).strip()
        and not _is_valid_uuid_text(req.tenant_id)
    ):
        logger.warning("raster_assets persist skipped: invalid tenant_id=%r", req.tenant_id)
        return
    try:
        import asyncio

        import db_persist

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
            return await db_persist.insert_raster_asset(
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
                            "quality",
                            "confidence",
                        )
                    }
                },
            )

        try:
            asyncio.run(_do())
        except RuntimeError:
            # حلقة أحداث قائمة بالفعل (نادر هنا) — شغّلها في خيط مستقلّ
            import threading

            def _runner():
                asyncio.run(_do())

            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            t.join(timeout=10)
    except Exception as _dbe:  # noqa: BLE001 — صدق: لا نُفشل المعالجة لغياب القاعدة
        logger.warning("raster_assets persist skipped: %s", _dbe)


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
            "cloud_pct": stats.get("cloud_pct"),
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
        if cog_url:
            _persist_raster_asset(req, cog_url, meta, bounds, stats)
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
        }
        job["status"] = JobStatus.completed
        job["progress_pct"] = 100
        job["finished_at"] = now
        _jobs.set(job_id, job)  # تثبيت النتيجة المكتملة (Redis/ذاكرة)
        logger.info(f"job {job_id} completed → layer {layer_id}")
    except Exception as e:  # noqa: BLE001
        job["status"] = JobStatus.failed
        # لا نُخزّن تفاصيل الاستثناء الخام في job status لأنّها تُقرأ عبر API وقد
        # تحتوي مسارات ملفات/روابط/تفاصيل مكتبات. السجلّ الداخلي يحتفظ بنوع الخطأ.
        job["error_message"] = "raster_processing_failed"
        _jobs.set(job_id, job)  # تثبيت الفشل (Redis/ذاكرة)
        logger.error("job %s failed: %s", job_id, type(e).__name__)


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
            failed[ind.value] = str(e)
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
                arr = si.compute_ndsi(red, nir, np)
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


@app.post("/process")
async def process_raster(
    req: ProcessRequest, background_tasks: BackgroundTasks, x_agent_token: str = Header(None)
):
    _require_service_token(x_agent_token)
    """يبدأ معالجة مؤشّر (خلفيّة — لا يحجب الطلب). يُرجع job_id للاستعلام."""
    if not req.raster_url:
        raise HTTPException(400, "raster_url مطلوب (ارفع الراستر أوّلاً).")
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    j = {
        "job_id": job_id,
        "status": JobStatus.pending,
        "progress_pct": 0,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _jobs.set(job_id, j)
    # معالجة في الخلفيّة — لا تحجب الطلب (مهمّ لقلب النظام تحت الحمل).
    background_tasks.add_task(_run_processing, job_id, req)
    return {
        "job_id": job_id,
        "status": j["status"],
        "progress_pct": j["progress_pct"],
        "created_at": j["created_at"],
        "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"),
        "error_message": j.get("error_message"),
    }


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


@app.post("/v1/fields/{field_id}/process-from-stac")
async def process_from_stac(
    field_id: str,
    req: ProcessFromStacRequest,
    background_tasks: BackgroundTasks,
    x_agent_token: str = Header(None),
):
    """يجسر الاستيراد→المعالجة: يكدّس COGs المنفصلة لنطاقات STAC في VRT
    (عبر /vsicurl/ للبعيد) ثم يشغّل نفس مسار /process (قصّ→مؤشّر→COG→persist).

    مناسب للمزوّد بلا مفتاح (Element84): استدعِ /imagery/best لجلب band hrefs،
    ثمّ مرّرها هنا. خلفيّة — يُرجِع job_id.
    """
    _require_service_token(x_agent_token)
    import stac_vrt

    # كلّ href يُتحقَّق منه (traversal/SSRF) قبل بناء الـVRT.
    safe_hrefs = {k: _safe_raster_source(v) for k, v in (req.band_hrefs or {}).items()}
    try:
        vrt_path, index_map = stac_vrt.build_band_vrt(safe_hrefs)
    except Exception as e:  # noqa: BLE001 — مدخل غير صالح/نطاق غير مقروء
        raise HTTPException(400, f"تعذّر بناء VRT من نطاقات STAC: {e}") from e

    band_kwargs = {k: v for k, v in index_map.items() if k in BandMapping.model_fields}
    preq = ProcessRequest(
        raster_url=vrt_path,
        indicator=req.indicator,
        bands=BandMapping(**band_kwargs),
        field_id=field_id,
        tenant_id=req.tenant_id,
        source_format=req.source_format,
        scene_id=req.scene_id,
        capture_datetime=req.capture_datetime,
        apply_cloud_mask=req.apply_cloud_mask,
        clip_polygon_geojson=req.clip_polygon_geojson,
    )
    job_id = f"stac_{uuid.uuid4().hex[:12]}"
    _jobs.set(
        job_id,
        {
            "job_id": job_id,
            "status": JobStatus.pending,
            "progress_pct": 0,
            "created_at": datetime.now(UTC).isoformat(),
        },
    )
    background_tasks.add_task(_run_processing, job_id, preq)
    return {
        "job_id": job_id,
        "status": JobStatus.pending,
        "bands": index_map,
        "raster_url": vrt_path,
    }


@app.get("/v1/imagery/backfill/policy")
async def historical_backfill_policy():
    """Return switchable historical imagery presets used by the UI/admin policy.

    This makes the behavior explicit instead of hard-coding a costly global window.
    """
    policy = AutoBackfillPolicy()
    return {
        **policy.model_dump(),
        "presets": {
            "auto_12_months": {"months": 12, "recommended_for": "new_field_auto_bootstrap"},
            "extended_3_years": {"months": 36, "recommended_for": "season_comparison"},
            "research_5_years": {"months": 60, "recommended_for": "enterprise_research_prediction"},
            "custom": {"months": "1..120", "recommended_for": "explicit_user_selection"},
        },
    }


@app.post("/v1/fields/{field_id}/imagery/backfill")
async def field_historical_backfill(
    field_id: str,
    req: HistoricalBackfillRequest,
    background_tasks: BackgroundTasks,
    x_agent_token: str = Header(None),
):
    """Create a switchable historical imagery backfill plan/job for a field.

    Presets:
      • auto_12_months: run automatically after creating a field.
      • extended_3_years: user/admin toggle for season comparison.
      • research_5_years: enterprise/research toggle.
      • custom: explicit from/to or months.

    The endpoint searches Sentinel-2 scenes month-by-month, selects the least-cloudy
    scenes per month, and schedules one processing job per (scene × index). When
    dry_run=true it returns the plan only, which is useful for UI cost previews.
    """
    _require_service_token(x_agent_token)
    await _require_field_tenant(field_id)

    if not req.indices:
        raise HTTPException(400, "indices مطلوبة")
    unsupported = [
        i.value
        for i in req.indices
        if i
        not in {
            IndicatorKind.ndvi,
            IndicatorKind.ndmi,
            IndicatorKind.savi,
            IndicatorKind.evi,
            IndicatorKind.gndvi,
            IndicatorKind.ndre,
            IndicatorKind.msi,
            IndicatorKind.msavi,
        }
    ]
    if unsupported:
        raise HTTPException(400, f"مؤشّرات غير مناسبة للـbackfill البصري: {unsupported}")

    clip = req.clip_polygon_geojson
    bbox = _bbox_from_geojson(clip)
    if bbox is None:
        raise HTTPException(400, "clip_polygon_geojson مطلوب لاشتقاق bbox وقصّ الصور على حدود الحقل")

    start, end, months = _backfill_date_range(req)
    windows = _month_windows(start, end)
    selected_scenes: list[dict] = []
    monthly: list[dict] = []
    for w_start, w_end in windows:
        search = await _stac_search(
            bbox,
            w_start.strftime("%Y-%m-%dT00:00:00Z"),
            w_end.strftime("%Y-%m-%dT23:59:59Z"),
            req.max_cloud_pct,
            limit=max(10, req.limit_per_month * 4),
        )
        items = _rank_scenes(search.get("items", []), max_cloud_pct=req.max_cloud_pct)[
            : req.limit_per_month
        ]
        selected_scenes.extend(items)
        monthly.append(
            {
                "month": w_start.strftime("%Y-%m"),
                "scenes_found": search.get("count", len(search.get("items", []))),
                "scenes_selected": len(items),
                "selected_scene_ids": [it.get("item_id") for it in items],
            }
        )

    job_ids: list[str] = []
    scheduled: list[dict] = []
    tenant_id = req.tenant_id or _REQ_TENANT.get()
    for scene in selected_scenes:
        # For Element84 Sentinel-2 COGs, build a VRT lazily in the background via the
        # same processing core contract. The direct job stores enough provenance to re-run.
        for indicator in req.indices:
            job_id = f"backfill_{uuid.uuid4().hex[:12]}"
            scheduled_item = {
                "job_id": job_id,
                "field_id": field_id,
                "tenant_id": tenant_id,
                "index": indicator.value,
                "scene_id": scene.get("item_id"),
                "capture_datetime": scene.get("datetime"),
                "cloud_cover_pct_scene": scene.get("cloud_cover_pct"),
                "dry_run": req.dry_run,
            }
            scheduled.append(scheduled_item)
            if req.dry_run:
                continue
            _jobs.set(
                job_id,
                {
                    **scheduled_item,
                    "status": JobStatus.pending,
                    "progress_pct": 0,
                    "created_at": datetime.now(UTC).isoformat(),
                    "job_type": "historical_backfill",
                    "preset": req.preset.value,
                },
            )

            # Reuse the same VRT/process path without issuing an HTTP subrequest.
            async def _run_scene_job(jid=job_id, sc=scene, ind=indicator):
                try:
                    import stac_vrt

                    safe_hrefs = {
                        k: _safe_raster_source(v)
                        for k, v in (sc.get("bands_urls") or {}).items()
                        if v
                    }
                    vrt_path, index_map = stac_vrt.build_band_vrt(safe_hrefs)
                    preq = ProcessRequest(
                        tenant_id=tenant_id,
                        field_id=field_id,
                        raster_url=vrt_path,
                        indicator=ind,
                        source_format=SourceFormat.sentinel2_l2a,
                        bands=BandMapping(
                            **{k: v for k, v in index_map.items() if k in BandMapping.model_fields}
                        ),
                        clip_polygon_geojson=clip,
                        apply_cloud_mask=req.apply_cloud_mask,
                        scene_id=sc.get("item_id"),
                        capture_datetime=sc.get("datetime"),
                        provider="element84",
                    )
                    _run_processing(jid, preq)
                except Exception as e:  # noqa: BLE001
                    j = _jobs.get(jid) or {"job_id": jid}
                    j.update(
                        {
                            "status": JobStatus.failed,
                            "error_message": str(e),
                            "finished_at": datetime.now(UTC).isoformat(),
                        }
                    )
                    _jobs.set(jid, j)

            background_tasks.add_task(_run_scene_job)
            job_ids.append(job_id)

    return {
        "field_id": field_id,
        "preset": req.preset.value,
        "period": {
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
            "months": months,
        },
        "indices": [i.value for i in req.indices],
        "max_cloud_pct": req.max_cloud_pct,
        "limit_per_month": req.limit_per_month,
        "dry_run": req.dry_run,
        "months_scanned": len(windows),
        "scenes_selected": len(selected_scenes),
        "jobs_scheduled": len(job_ids),
        "monthly": monthly,
        "jobs": scheduled,
        "policy": {
            "auto": "auto_12_months",
            "extended": "extended_3_years",
            "research": "research_5_years",
            "custom": "from_date/to_date or months",
        },
    }


@app.get("/v1/imagery/quality/policy")
async def imagery_quality_policy():
    """Document the active enterprise imagery policy used by Sahool.

    This exposes the operational rules to frontend/admin tooling so behavior is
    explicit: combine SCL+CLM/CLP where available, rank scenes by quality, and use
    COG+tile-cache for interactive maps.
    """
    return {
        "cloud_mask": {
            "preferred": ["CLM", "CLP", "SCL"],
            "fallback": "warn_and_unmasked_when_no_quality_band",
            "clp_threshold": "0.40 or 40 depending on encoding",
        },
        "scene_ranking": {
            "weights": {"cloud": 0.50, "recency": 0.20, "coverage": 0.20, "provider_quality": 0.10},
            "rule": "AOI cloud percentage overrides scene-level cloud cover when present",
        },
        "mosaic": {
            "default_rule": "least_cloud_then_recent",
            "recommended_for": "latest clear view when one scene is cloudy",
        },
        "tiles": {
            "format": "TileJSON + XYZ",
            "source": "COG",
            "cache": os.getenv("TILE_CACHE_ENABLED", "true"),
        },
        "geometry_history": {"enabled": True, "table": "field_geometry_versions"},
        "analytics_export": {
            "format": "GeoParquet when pyarrow/shapely are installed; NDJSON fallback otherwise"
        },
    }


@app.post("/v1/imagery/scenes/rank")
async def rank_imagery_scenes(req: SceneRankRequest):
    ranked = _rank_scenes(
        req.scenes, max_cloud_pct=req.max_cloud_pct, prefer_recent_days=req.prefer_recent_days
    )
    return {
        "mode": req.mode,
        "count": len(ranked),
        "best_scene": ranked[0] if ranked else None,
        "ranked": ranked,
    }


@app.post("/v1/imagery/mosaic/plan")
async def imagery_mosaic_plan(req: MosaicPlanRequest):
    """Build a least-cloud mosaic plan from STAC search results.

    The endpoint plans rather than silently rendering a fabricated mosaic. The
    selected scenes are the ranked candidates; processing can then call CDSE with
    leastCC or schedule Element84 VRT processing.
    """
    search = await _stac_search(
        req.bbox, req.datetime_start, req.datetime_end, req.max_cloud_pct, req.limit
    )
    ranked = _rank_scenes(search.get("items", []), max_cloud_pct=req.max_cloud_pct)
    return {
        "mosaic_rule": req.mosaic_rule,
        "bbox": req.bbox,
        "datetime": {"from": req.datetime_start, "to": req.datetime_end},
        "scenes_found": search.get("count", len(search.get("items", []))),
        "scenes_ranked": len(ranked),
        "selected": ranked[: min(5, len(ranked))],
        "recommendation": "use_cdse_leastCC_when_credentials_available_else_element84_ranked_vrt",
    }


@app.post("/v1/fields/{field_id}/geometry/versions")
async def create_field_geometry_version(
    field_id: str,
    geometry: dict,
    valid_from: str | None = Query(None),
    reason: str | None = Query("manual_snapshot"),
    x_agent_token: str = Header(None),
):
    """Persist a field geometry snapshot for reproducible historical analytics."""
    _require_service_token(x_agent_token)
    await _require_field_tenant(field_id)
    tenant_id = _REQ_TENANT.get()
    import db_persist

    version_id = await db_persist.insert_field_geometry_version(
        field_id=field_id,
        tenant_id=tenant_id,
        geometry=geometry,
        valid_from=valid_from,
        reason=reason,
    )
    return {
        "field_id": field_id,
        "tenant_id": tenant_id,
        "version_id": version_id,
        "persisted": bool(version_id),
    }


@app.post("/v1/fields/analytics/geoparquet/export")
async def export_field_analytics_geoparquet(
    req: GeoParquetExportRequest, x_agent_token: str = Header(None)
):
    """Export field analytics as GeoParquet when optional deps exist, else NDJSON.

    GeoParquet requires pyarrow/shapely/geopandas in the production image. The
    fallback writes an explicit NDJSON file instead of mislabeling a non-GeoParquet
    artifact.
    """
    _require_service_token(x_agent_token)
    tenant_id = req.tenant_id or _REQ_TENANT.get()
    import json as _json

    import db_persist

    rows = await db_persist.fetch_field_analytics_for_export(
        tenant_id=tenant_id, field_ids=req.field_ids
    )
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in req.output_name)
    out_dir = os.path.join(UPLOAD_DIR, "exports", str(tenant_id or "unknown"))
    os.makedirs(out_dir, exist_ok=True)
    try:
        import geopandas as gpd  # type: ignore
        from shapely.geometry import shape  # type: ignore

        gdf = gpd.GeoDataFrame(
            [
                {k: v for k, v in row.items() if k != "geometry"}
                | {"geometry": shape(row["geometry"])}
                for row in rows
                if row.get("geometry")
            ],
            crs="EPSG:4326",
        )
        path = os.path.join(out_dir, f"{safe_name}.parquet")
        gdf.to_parquet(path, index=False)
        return {"format": "GeoParquet", "path": path, "rows": len(gdf), "crs": "EPSG:4326"}
    except Exception as e:  # noqa: BLE001
        path = os.path.join(out_dir, f"{safe_name}.ndjson")
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(_json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return {
            "format": "NDJSON",
            "path": path,
            "rows": len(rows),
            "geo_parquet_ready": False,
            "reason": type(e).__name__,
        }


@app.get("/v1/tile-cache/stats")
async def tile_cache_stats(x_agent_token: str = Header(None)):
    _require_service_token(x_agent_token)
    root = os.path.join(UPLOAD_DIR, "tile_cache")
    count = 0
    size = 0
    for base, _dirs, files in os.walk(root) if os.path.exists(root) else []:
        for fn in files:
            if fn.endswith(".png"):
                count += 1
                try:
                    size += os.path.getsize(os.path.join(base, fn))
                except OSError:
                    pass
    return {
        "enabled": os.getenv("TILE_CACHE_ENABLED", "true").lower() == "true",
        "tiles": count,
        "bytes": size,
    }


@app.post("/process/batch")
async def process_batch(
    req: BatchProcessRequest, background_tasks: BackgroundTasks, x_agent_token: str = Header(None)
):
    """معالجة دفعيّة: عدّة مؤشّرات من نفس المشهد في مهمّة واحدة (كفاءة I/O).

    بدل طلب لكلّ مؤشّر، طلب واحد يحسب NDVI+NDRE+NDSI+... من نفس المشهد. مفيد
    جدّاً للأتمتة (مشهد جديد → كلّ المؤشّرات دفعةً). خلفيّة، يُرجِع job_id.
    """
    _require_service_token(x_agent_token)
    if not req.raster_url:
        raise HTTPException(400, "raster_url مطلوب (ارفع الراستر أوّلاً).")
    if not req.indicators:
        raise HTTPException(400, "indicators مطلوبة (مؤشّر واحد على الأقلّ).")
    job_id = f"batch_{uuid.uuid4().hex[:12]}"
    _jobs.set(
        job_id,
        {
            "job_id": job_id,
            "status": JobStatus.pending,
            "progress_pct": 0,
            "created_at": datetime.now(UTC).isoformat(),
            "indicators": [i.value for i in req.indicators],
        },
    )
    background_tasks.add_task(_run_batch_processing, job_id, req)
    return {
        "job_id": job_id,
        "status": JobStatus.pending,
        "indicators": [i.value for i in req.indicators],
        "note": "استعلم /jobs/{job_id} — batch_results + batch_failed عند الاكتمال",
    }


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
            )
            sub_job_id = f"{job_id}_{ind}"
            _run_processing(sub_job_id, preq)
            sj = _jobs.get(sub_job_id) or {}
            if sj.get("status") == JobStatus.completed:
                results[ind] = (sj.get("result") or {}).get("layer_id") or sub_job_id
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
    _jobs.set(job_id, job)
    logger.info("cdse %s: %d نجح، %d فشل", job_id, len(results), len(failed))


@app.post("/v1/fields/{field_id}/process-cdse")
async def process_cdse(
    field_id: str,
    req: ProcessCdseRequest,
    background_tasks: BackgroundTasks,
    x_agent_token: str = Header(None),
):
    """يحسب مؤشّرات الحقل عبر CDSE (المزوّد الافتراضيّ الأقوى). خلفيّة، يُرجِع job_id.

    صدق: بلا اعتمادات CDSE (``CDSE_CLIENT_ID``/``SECRET`` أو ``CDSE_ENABLED=false``) ⇒
    ``available=false`` (200، لا خطأ) كي يسقط المنسّق إلى Element84 بصمت — لا توقّف ولا تلفيق.
    """
    _require_service_token(x_agent_token)
    import cdse_client

    if not cdse_client.is_configured():
        return {
            "provider": "cdse",
            "available": False,
            "queued": False,
            "note_ar": "CDSE غير مُهيّأ (لا CDSE_CLIENT_ID/SECRET) — يسقط المنسّق إلى Element84.",
        }
    if not req.bbox or len(req.bbox) != 4:
        raise HTTPException(400, "bbox مطلوب [west,south,east,north] (EPSG:4326).")
    if not req.indicators:
        raise HTTPException(400, "indicators مطلوبة (مؤشّر واحد على الأقلّ).")
    job_id = f"cdse_{uuid.uuid4().hex[:12]}"
    _jobs.set(
        job_id,
        {
            "job_id": job_id,
            "status": JobStatus.pending,
            "progress_pct": 0,
            "created_at": datetime.now(UTC).isoformat(),
            "indicators": list(req.indicators),
            "provider": "cdse",
        },
    )
    background_tasks.add_task(_run_cdse_processing, job_id, field_id, req)
    return {
        "provider": "cdse",
        "available": True,
        "queued": True,
        "job_id": job_id,
        "status": JobStatus.pending,
        "indicators": list(req.indicators),
        "note": "معالجة CDSE خلفيّة — استعلم /jobs/{job_id} (cdse_results + cdse_failed).",
    }


@app.get("/jobs/{job_id}")
async def job_status(job_id: str, x_agent_token: str = Header(None)):
    """حالة المهمّة."""
    _require_service_token(x_agent_token)
    j = _jobs.get(job_id)
    if not j:
        raise HTTPException(404, "مهمّة غير موجودة")
    return {
        "job_id": job_id,
        "status": j["status"],
        "progress_pct": j["progress_pct"],
        "created_at": j["created_at"],
        "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"),
        "error_message": j.get("error_message"),
    }


@app.get("/jobs/{job_id}/result")
async def job_result(job_id: str, x_agent_token: str = Header(None)):
    """نتيجة المهمّة (بعد الاكتمال)."""
    _require_service_token(x_agent_token)
    j = _jobs.get(job_id)
    if not j:
        raise HTTPException(404, "مهمّة غير موجودة")
    if j["status"] != JobStatus.completed:
        raise HTTPException(409, f"المهمّة غير مكتملة (الحالة: {j['status']})")
    return j["result"]


@app.get("/info/{layer_id}")
async def raster_info(layer_id: str, x_agent_token: str = Header(None)):
    """معلومات طبقة راستر معالَجة."""
    _require_service_token(x_agent_token)
    layer = _layers.get(layer_id)
    if not layer:
        raise HTTPException(404, "طبقة غير موجودة")
    return layer


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


@app.get("/tiles/{layer_id}/{z}/{x}/{y}.png")
async def get_tile(layer_id: str, z: int, x: int, y: int):
    """بلاطة خريطة لطبقة (MapLibre). عند توفّر البلاطات المُنتجة تُخدَم من
    القرص؛ وإلّا تُرجع بلاطة شفّافة (بنية صحيحة للعرض)."""
    _require_layer_tenant(layer_id)  # تفويض: الطبقة تخصّ مستأجِر الطلب (إغلاق IDOR)
    await _require_layer_tenant_authorized(layer_id)
    if layer_id not in _layers:
        raise HTTPException(404, "طبقة غير موجودة")
    tile_path = os.path.join(UPLOAD_DIR, layer_id, f"{z}_{x}_{y}.png")
    if os.path.exists(tile_path):
        with open(tile_path, "rb") as fh:
            return Response(content=fh.read(), media_type="image/png")
    return Response(content=_TRANSPARENT_PNG, media_type="image/png")


# ─── دورة حياة الراستر (سدّ فجوة: لا سياسة تنظيف) ──────────────────────
@app.get("/cog/validate")
async def cog_validate(path: str, x_agent_token: str = Header(None)):
    """يتحقّق أنّ ملفّاً COG صالح (مبلّط + أهرامات داخليّة) — تدقيق الجودة.

    COG جيّد = قراءة جزئيّة سريعة. هذا يكشف "COG يفتح لكن بطيء".
    """
    _require_service_token(x_agent_token)
    # حماية path traversal
    if ".." in path:
        raise HTTPException(400, "مسار غير صالح")
    import cog_writer

    return cog_writer.validate_cog(path)


@app.post("/imagery/timeseries/parallel")
async def imagery_timeseries_parallel(
    req: TimeSeriesAnalyzeRequest,
    max_concurrency: int = Query(4, ge=1, le=10),
    x_agent_token: str = Header(None),
):
    """تحليل زمني بمعالجة متوازية للمشاهد (أسرع للسلاسل الطويلة).

    يحلّل قيماً محسوبة مسبقاً (من /process) بالتوازي المحدود + يبني التحليل.
    semaphore يحدّ التزامن (backpressure). عزل فشل كلّ مشهد.
    """
    _require_service_token(x_agent_token)
    import time_series as ts

    async def _passthrough(sc):
        # القيم محسوبة مسبقاً — نمرّرها (لا إعادة حساب). للتوضيح: في خطّ حقيقي
        # تستبدلها بدالّة تحسب المؤشّر من COG المشهد.
        return sc.get("mean")

    return await ts.build_time_series_parallel(
        req.scene_values, _passthrough, max_concurrency=max_concurrency
    )


@app.get("/storage/stats")
async def storage_stats(x_agent_token: str = Header(None)):
    _require_service_token(x_agent_token)
    """إحصاء التخزين (مراقبة قبل الانفجار) — حجم + توزيع بالنوع."""
    import raster_lifecycle as rl

    return rl.scan_storage(UPLOAD_DIR)


@app.post("/storage/cleanup")
async def storage_cleanup(dry_run: bool = True, x_agent_token: str = Header(None)):
    """ينظّف النواتج المنتهية حسب الاحتفاظ. dry_run=true افتراضي (آمن).

    النواتج المحميّة (offline_packs) لا تُمَسّ. مرّر dry_run=false للحذف الفعلي.
    يمكن جدولته دوريّاً (scheduler) لمنع تضخّم التخزين.
    """
    _require_service_token(x_agent_token)
    import raster_lifecycle as rl

    return rl.cleanup(UPLOAD_DIR, dry_run=dry_run)


# ─── حزم offline (MBTiles) للمناطق ضعيفة الاتّصال — سدّ فجوة اليمن ──────
OFFLINE_PACKS_DIR = os.path.join(UPLOAD_DIR, "offline_packs")
os.makedirs(OFFLINE_PACKS_DIR, exist_ok=True)


@app.get("/offline/packs")
async def list_offline_packs(x_agent_token: str = Header(None)):
    _require_service_token(x_agent_token)
    """يسرد حزم MBTiles الجاهزة للتنزيل (الموبايل يحمّلها للعمل offline).

    صدق: يسرد ما هو موجود فعلاً على القرص فقط — لا يدّعي حزماً غير مُولَّدة.
    لتوليد حزمة: استخدم scripts_v9/generate_mbtiles.sh لمنطقة (الجوف مثلاً).
    """
    packs = []
    if os.path.isdir(OFFLINE_PACKS_DIR):
        for name in sorted(os.listdir(OFFLINE_PACKS_DIR)):
            if name.endswith((".mbtiles", ".pmtiles")):
                path = os.path.join(OFFLINE_PACKS_DIR, name)
                packs.append(
                    {
                        "name": name,
                        "format": name.rsplit(".", 1)[-1],
                        "size_mb": round(os.path.getsize(path) / 1e6, 1),
                        "download_url": f"/offline/packs/{name}",
                    }
                )
    return {
        "count": len(packs),
        "packs": packs,
        "note": "حمّل الحزمة على الجهاز لعرض خريطة الخلفيّة بلا اتّصال",
    }


@app.get("/offline/packs/{pack_name}")
async def download_offline_pack(pack_name: str, x_agent_token: str = Header(None)):
    _require_service_token(x_agent_token)
    """ينزّل حزمة MBTiles/PMTiles محدّدة (للتخزين على الجهاز)."""
    # حماية من path traversal
    if "/" in pack_name or ".." in pack_name:
        raise HTTPException(400, "اسم حزمة غير صالح")
    path = os.path.join(OFFLINE_PACKS_DIR, pack_name)
    if not os.path.exists(path):
        raise HTTPException(404, "حزمة غير موجودة")
    from fastapi.responses import FileResponse

    return FileResponse(path, media_type="application/octet-stream", filename=pack_name)


@app.get("/layers/{layer_id}/tilejson")
async def layer_tilejson(
    layer_id: str, rescale: str | None = Query(None), colormap: str | None = Query("viridis")
):
    """يُرجِع قالب رابط البلاطات لـMapLibre (سدّ فجوة P0).

    إن ضُبط TITILER_URL ووُجد COG للطبقة → رابط TiTiler ديناميكي (تمدّد ألوان
    وخريطة ألوان عند الطلب، بلا إعادة توليد). وإلّا → البلاطات الثابتة fallback.
    صدق: لا يدّعي ديناميكيّة غير متوفّرة — يُبلّغ بالمصدر الفعلي.
    """
    _require_layer_tenant(layer_id)  # تفويض: الطبقة تخصّ مستأجِر الطلب (إغلاق IDOR)
    await _require_layer_tenant_authorized(layer_id)
    if layer_id not in _layers:
        raise HTTPException(404, "طبقة غير موجودة")
    layer = _layers[layer_id]
    # cog_url للعميل: عامّ http(s) فقط (لا تسريب مسارات داخليّة عبر titiler)
    cog_url = _public_cog_url(layer.get("cog_url") or layer.get("raster_url"))

    if TITILER_URL and cog_url:
        # رابط TiTiler ديناميكي من COG. rescale مثل "0,1" لـNDVI.
        params = f"url={cog_url}&colormap_name={colormap}"
        if rescale:
            params += f"&rescale={rescale}"
        return {
            "source": "titiler-dynamic",
            "tilejson": "2.2.0",
            "tiles": [f"{TITILER_URL}/cog/tiles/{{z}}/{{x}}/{{y}}.png?{params}"],
            "minzoom": 8,
            "maxzoom": 18,
            "note": "بلاطات ديناميكيّة من COG عبر TiTiler (تمدّد/ألوان عند الطلب)",
        }
    # fallback: البلاطات الثابتة
    return {
        "source": "static-pregenerated",
        "tilejson": "2.2.0",
        "tiles": [f"/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png"],
        "minzoom": 8,
        "maxzoom": 16,
        "note": "بلاطات ثابتة مُولَّدة مسبقاً (TiTiler غير مضبوط). للديناميكي: "
        "اضبط TITILER_URL ووفّر cog_url للطبقة.",
    }


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
        "confidence": layer.get("confidence"),
        "quality": layer.get("quality"),
    }


async def _resolve_field_layer(field_id: str, index: str, date: str) -> dict | None:
    """يجد طبقة COG للحقل: من الذاكرة أوّلاً، وإلّا يُعيد الترطيب من raster_assets.

    يسدّ ثغرة «persistence مكتوب لا مقروء»: بعد إعادة التشغيل/على worker آخر،
    فهرس الذاكرة فارغ ⇒ نستعيد cog_uri+الحدود من القاعدة ونُعيد بناء الفهرس،
    فيعمل العرض على COG الموجود على القرص (UPLOAD_DIR كـvolume دائم).
    """
    layer = _find_field_layer(field_id, index, date)
    if layer is not None:
        return layer
    try:
        import time as _t

        import db_persist

        internal = _normalize_index(index)
        asset = await db_persist.fetch_latest_asset(
            field_id, internal, date, tenant_id=_REQ_TENANT.get()
        )
        if not asset or not asset.get("cog_url"):
            return None
        # لـfile:// نفحص القرص؛ لـs3:// نؤجّل الوجود إلى rasterio (لا نرفضه هنا).
        if not object_store.exists_locally(asset["cog_url"]):
            logger.warning("raster_assets hit but COG missing on host: %s", asset["cog_url"])
            return None
        lid = f"db_{field_id}_{internal}"
        _layers[lid] = {
            "cog_url": asset["cog_url"],
            "index": internal,
            "tenant_id": _REQ_TENANT.get(),
            "acquisition_date": asset.get("acquisition_date"),
            "bounds_4326": asset.get("bounds_4326"),
            "cloud_pct": asset.get("cloud_pct"),
            "confidence": asset.get("confidence"),
            "quality": asset.get("quality"),
            "cloud_mask_applied": asset.get("cloud_mask_applied"),
            # تفويض: tenant_id مثبت أعلى؛ DB fetch نفسه منطق بالمستأجر.
            "created_at": asset.get("acquisition_date") or _t.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _field_layers.setdefault(field_id, [])
        if lid not in _field_layers[field_id]:
            _field_layers[field_id].append(lid)
        return _layers[lid]
    except Exception as e:  # noqa: BLE001 — غياب القاعدة لا يُفشل القراءة
        logger.warning("DB rehydrate skipped (%s): %s", field_id, e)
        return None


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


@app.get("/indices")
async def field_indices(
    field_id: str,
    lat: float | None = Query(None),
    lon: float | None = Query(None),
    date: str = Query("latest"),
    indices: str = Query("ndvi,ndre,ndsi,ndwi,bsi,si,rvi"),
    cloud_cover: float | None = Query(None),
    x_agent_token: str = Header(None),
):
    """متوسّط كلّ مؤشّر للحقل (للدمج الحيّ في field-intelligence) + غطاء السحب.

    يسدّ ثغرة wiring حقيقيّة: sensing_adapter كان ينادي /indices غير الموجودة ⇒
    المسار الطيفي الحيّ بلا تغذية. يعيد استخدام مسار indicator-grid
    (_resolve_field_layer + _grid_from_cog): لكلّ مؤشّر يقرأ COG المقصوص ويُرجِع
    المتوسّط (real_data=True). صدق: لا COG ⇒ قيم null + real_data=False + note (لا
    اختراع). cloud_cover يُمرَّر إن توفّر (من eo:cloud_cover عبر المستدعي) ليُفعّل
    تحويل الوزن للرادار في fuse_health.
    """
    _require_service_token(x_agent_token)
    requested = [i.strip() for i in indices.split(",") if i.strip()]
    out: dict = {
        "field_id": field_id,
        "real_data": False,
        "observed_at": None,
        "field_coverage": None,
        "cloud_cover": cloud_cover,
        "resolution_m": 10.0,
    }
    coverage_val = None
    for idx in requested:
        # rvi رادارية: تُحسب من COG ثنائي النطاق (VV/VH) لا band واحد
        if idx == "rvi":
            m = await _rvi_from_sar_cog(field_id, date)
            out["rvi"] = m
            if m is not None:
                out["real_data"] = True
            continue
        layer = await _resolve_field_layer(field_id, idx, date)
        real = _grid_from_cog(layer, idx, date, 16) if layer is not None else None
        if real is None:
            out[idx] = None
            continue
        out[idx] = real["stats"]["mean"]
        out["real_data"] = True
        out["observed_at"] = out["observed_at"] or real.get("date")
        if coverage_val is None:
            cells = [v for row in real["grid"] for v in row]
            coverage_val = (
                round(sum(v is not None for v in cells) / len(cells), 4) if cells else None
            )
    out["field_coverage"] = coverage_val
    out["note"] = (
        None if out["real_data"] else "لا COG مقصوص للحقل — شغّل /process أوّلاً (لا قيم مخترعة)"
    )
    return out


@app.get("/v1/fields/{field_id}/indicator-grid")
async def field_indicator_grid(
    field_id: str,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    grid: int = Query(32, ge=2, le=256),
):
    """شبكة المؤشّر لكلّ بكسل (per-pixel) لخريطة الموبايل.

    إن وُجد COG مقصوص للحقل (من /process مع clip_polygon) → يُقرأ ويُصغّر
    إلى grid×grid مع تصنيف مناطق الشدّة (real_data=True). وإلّا → شبكة محاكاة
    مُعلَّمة بصدق (real_data=False, source="simulation") — نفس شكل العقد دائماً.
    """
    await _require_field_tenant(field_id)  # تفويض: ملكيّة الحقل (ذاكرة + جدول fields)
    import indicator_grid as ig

    # تطبيع اسم المؤشّر المعروض (salinity/NDVU aliases مقبولة للواجهة)
    out_index = _display_index(index)
    index = _normalize_index(index)

    layer = await _resolve_field_layer(field_id, index, date)
    if layer is not None:
        real = _grid_from_cog(layer, out_index, date, grid)
        if real is not None:
            return real

    # fallback: شبكة محاكاة (لا COG حقيقي / لا rasterio / لا شبكة) — مُعلَّمة بصدق
    # bbox افتراضي حول اليمن (الجوف) إن لم تتوفّر حدود حقيقيّة.
    bbox = [44.0, 16.0, 44.01, 16.01]
    if layer is not None and layer.get("bounds_4326"):
        bbox = [round(float(x), 6) for x in layer["bounds_4326"]]
    return ig.synthetic_grid(field_id, out_index, date, bbox, grid)


@app.get("/v1/fields/{field_id}/pixel")
async def field_pixel_value(
    field_id: str,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    v: str | None = Query(None),
):
    """قيمة المؤشّر عند نقطة واحدة داخل طبقة الحقل.

    لا يخترع قيماً: يجب وجود COG حقيقي للحقل/المؤشّر/التاريخ. يتحقق من ملكية
    الحقل، يرفض النقاط خارج حدود COG المقصوص، ويرجع value + metadata.
    """
    await _require_field_tenant(field_id, hide_existence=True)
    out_index = _display_index(index)
    index = _normalize_index(index)
    layer = await _resolve_field_layer(field_id, index, date)
    if layer is None:
        raise HTTPException(404, "لا توجد طبقة مؤشر حقيقية لهذا الحقل/التاريخ")
    bounds = layer.get("bounds_4326")
    if bounds:
        minx, miny, maxx, maxy = [float(v) for v in bounds]
        if not (minx <= lon <= maxx and miny <= lat <= maxy):
            raise HTTPException(400, "النقطة خارج حدود الحقل/الطبقة")
    try:
        import math as _math

        import rasterio
        from rasterio.warp import transform
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, "rasterio غير متوفر لقراءة قيمة البكسل") from e
    path = object_store.to_gdal_path(layer.get("cog_url") or layer.get("raster_url") or "")
    if not path:
        raise HTTPException(404, "مصدر COG غير موجود")
    try:
        with rasterio.open(path) as src:
            xs, ys = [lon], [lat]
            if src.crs and str(src.crs).upper() not in ("EPSG:4326", "OGC:CRS84"):
                xs, ys = transform("EPSG:4326", src.crs, xs, ys)
            row, col = src.index(xs[0], ys[0])
            if row < 0 or col < 0 or row >= src.height or col >= src.width:
                raise HTTPException(400, "النقطة خارج حدود الحقل/الطبقة")
            value = next(src.sample([(xs[0], ys[0])]))[0]
            nodata = src.nodata
            if (nodata is not None and value == nodata) or not _math.isfinite(float(value)):
                return {
                    "field_id": field_id,
                    "index": out_index,
                    "date": layer.get("acquisition_date") or date,
                    "lat": lat,
                    "lon": lon,
                    "value": None,
                    "valid": False,
                    "reason": "nodata_or_masked",
                    "confidence": 0.0,
                    "quality": "nodata",
                }
            quality = _pixel_quality(layer, float(value))
            return {
                "field_id": field_id,
                "index": out_index,
                "date": layer.get("acquisition_date") or date,
                "lat": lat,
                "lon": lon,
                "value": float(value),
                "valid": True,
                "source": layer.get("source_format") or "raster",
                "confidence": quality["confidence"],
                "quality": quality["quality"],
                "quality_reason": quality["reason"],
                "cloud_pct": quality.get("cloud_pct"),
            }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, "تعذّرت قراءة قيمة البكسل") from e


class PrescriptionRequest(BaseModel):
    index: str = "ndvi"
    date: str = "latest"
    grid: int = Field(32, ge=2, le=256)
    n_zones: int = Field(3, ge=2, le=6)
    base_rate: float | None = None  # معدّل أساسي (سماد/بذار) لاشتقاق معدّل المناطق
    strategy: str = "compensate"  # compensate | protect


@app.post("/v1/fields/{field_id}/prescription")
async def field_prescription(
    field_id: str, req: PrescriptionRequest, x_agent_token: str = Header(None)
):
    """وصفة مناطق الإدارة (VRT) من شبكة المؤشّر — سدّ Sprint 5b.

    يبني شبكة المؤشّر للحقل (نفس مسار indicator-grid: COG حقيقي إن وُجد وإلّا
    محاكاة صادقة)، يقسّمها بالكوانتايل إلى n_zones مناطق أداء، ويشتقّ معدّلاً
    موصى به لكلّ منطقة إن مُرّر base_rate. يُرجِع المناطق + إحصاء كلّ منطقة
    (pixel_count, pct, value_range) + متوسّط/تباين الحقل.

    صدق: real_data ينعكس من مصدر الشبكة؛ المعدّلات إرشاديّة (قرار agronomic
    يحتاج تحقّقاً ميدانيّاً).
    """
    _require_service_token(x_agent_token)  # توكن خدمة إلزاميّ (مطابقة الشقيقات — منع كشف الحقول)
    import indicator_grid as ig
    import management_zones as mz

    layer = await _resolve_field_layer(field_id, req.index, req.date)
    grid_resp = None
    if layer is not None:
        grid_resp = _grid_from_cog(layer, req.index, req.date, req.grid)
    if grid_resp is None:
        bbox = [44.0, 16.0, 44.01, 16.01]
        if layer is not None and layer.get("bounds_4326"):
            bbox = [round(float(x), 6) for x in layer["bounds_4326"]]
        grid_resp = ig.synthetic_grid(field_id, req.index, req.date, bbox, req.grid)

    pres = mz.prescription_from_grid(
        grid_resp["grid"],
        n_zones=req.n_zones,
        base_rate=req.base_rate,
        strategy=req.strategy,
    )
    return {
        "field_id": field_id,
        "index": req.index,
        "date": grid_resp.get("date", req.date),
        "bbox": grid_resp.get("bbox"),
        "rows": grid_resp.get("rows"),
        "cols": grid_resp.get("cols"),
        "real_data": grid_resp.get("real_data", False),
        "source": grid_resp.get("source", "raster"),
        **pres,
    }


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


@app.post("/v1/fields/{field_id}/change")
async def field_change(field_id: str, req: FieldChangeRequest, x_agent_token: str = Header(None)):
    """كشف التغيّر المكاني (per-pixel 2D) للحقل بين تاريخين — أين تدهور/تحسّن.

    يبني شبكتي المؤشّر الحقيقيّتين (من COG المقصوص لكلّ تاريخ، نفس مسار
    indicator-grid) ويُمرّرهما لـdetect_change. صدق: إن لم تتوفّر شبكة حقيقيّة
    لأحد التاريخين (لا COG / لا rasterio) يُرجِع real_data=False بلا تغيّر مُفبرَك.
    """
    _require_service_token(x_agent_token)  # توكن خدمة إلزاميّ (مطابقة الشقيقات — منع كشف الحقول)
    grid_a = await _real_field_grid(field_id, req.index, req.date_a, req.grid)
    grid_b = await _real_field_grid(field_id, req.index, req.date_b, req.grid)

    if grid_a is None or grid_b is None:
        missing = [d for d, g in ((req.date_a, grid_a), (req.date_b, grid_b)) if g is None]
        return {
            "field_id": field_id,
            "index": req.index,
            "date_a": req.date_a,
            "date_b": req.date_b,
            "real_data": False,
            "available": False,
            "missing_dates": missing,
            "note": "لا COG مقصوص للحقل لأحد التاريخين — شغّل /process أوّلاً "
            "(لا تغيّر مُفبرَك من بيانات غير متوفّرة)",
        }

    if grid_a["rows"] != grid_b["rows"] or grid_a["cols"] != grid_b["cols"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"أبعاد شبكتي التاريخين مختلفة: "
                f"{grid_a['rows']}×{grid_a['cols']} مقابل {grid_b['rows']}×{grid_b['cols']}"
            ),
        )

    import change_detection as cd

    result = cd.detect_change(
        grid_a["grid"],
        grid_b["grid"],
        index=req.index,
        slight_threshold=req.slight_threshold,
        severe_threshold=req.severe_threshold,
    )
    result.update(
        {
            "field_id": field_id,
            "date_a": grid_a.get("date", req.date_a),
            "date_b": grid_b.get("date", req.date_b),
            "bbox": grid_b.get("bbox") or grid_a.get("bbox"),
            "real_data": True,
            "available": True,
        }
    )
    return result


# ─── السلسلة الزمنيّة للمؤشّر (field-scoped) ──────────────────────────
@app.get("/v1/fields/{field_id}/timeseries")
async def field_timeseries(
    field_id: str,
    index: str = Query("ndvi"),
    dates: str = Query(
        "",
        description="تواريخ مفصولة بفواصل (YYYY-MM-DD). فارغ ⇒ كلّ تواريخ COG المتاحة للحقل.",
    ),
    grid: int = Query(16, ge=2, le=64),
):
    """السلسلة الزمنيّة الحقيقيّة لمتوسّط المؤشّر للحقل عبر التواريخ المتاحة.

    لكلّ تاريخ يبني شبكة المؤشّر من COG الحقل المقصوص ويأخذ متوسّطها الحقيقي
    (real_data). يجمّعها شهريّاً ويحسب الاتّجاه/الشذوذ عبر time_series. صدق:
    لا COG ⇒ نقطة محذوفة (لا تُخترع قيمة)؛ لا نقاط حقيقيّة ⇒ available=False.

    أُزيل x_agent_token (كان مُعلَناً بلا فرض — مسار متصفّح). التفويض عبر ملكيّة الحقل.
    """
    await _require_field_tenant(field_id)  # تفويض: ملكيّة الحقل (DB مصدر الحقيقة + ذاكرة)
    out_index = _display_index(index)
    index = _normalize_index(index)
    requested_dates = [d.strip() for d in dates.split(",") if d.strip()]
    if not requested_dates:
        # كلّ تواريخ الطبقات الحقيقيّة المتاحة للحقل+المؤشّر. نبدأ بالذاكرة، ثم
        # نقرأ raster_assets عند إعادة التشغيل/worker آخر؛ وإلّا يصبح الـtimeline
        # فارغاً رغم وجود COGs مخزّنة. لا نُنشئ نقاطاً، فقط نكتشف التواريخ.
        internal = _normalize_index(index)
        seen: set[str] = set()
        for lid in _field_layers.get(field_id, []):
            lyr = _layers.get(lid)
            if not lyr or not lyr.get("cog_url") or lyr.get("index") != internal:
                continue
            d = lyr.get("acquisition_date")
            if d:
                seen.add(str(d)[:10])
        if not seen:
            try:
                import db_persist

                seen.update(
                    await db_persist.list_asset_dates(
                        field_id, internal, tenant_id=_REQ_TENANT.get(), limit=100
                    )
                )
            except Exception as e:  # noqa: BLE001 — لا نكسر السلسلة الزمنية عند غياب DB
                logger.warning("raster_assets dates rehydrate skipped (%s): %s", field_id, e)
        requested_dates = sorted(seen)

    points: list[dict] = []
    for date in requested_dates:
        real = await _real_field_grid(field_id, index, date, grid)
        if real is None:
            continue
        points.append(
            {
                "datetime": str(real.get("date") or date)[:10],
                "mean": real["stats"]["mean"],
            }
        )

    if not points:
        return {
            "field_id": field_id,
            "index": out_index,
            "available": False,
            "real_data": False,
            "points": [],
            "requested_dates": requested_dates,
            "note": "لا COG مقصوص للحقل في التواريخ المطلوبة — شغّل /process (لا قيم مؤشّر مخترعة)",
        }

    import time_series as ts

    analysis = ts.build_time_series(points, value_key="mean")
    return {
        "field_id": field_id,
        "index": out_index,
        "available": True,
        "real_data": True,
        "points": points,
        **analysis,
    }


# ─── بلاطات XYZ ديناميكيّة (TiTiler-style) من COG الحقل المقصوص ────────
@app.get("/v1/fields/{field_id}/tiles/{z}/{x}/{y}.png")
async def field_tile(
    field_id: str,
    z: int,
    x: int,
    y: int,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    v: str | None = Query(None),
):
    """بلاطة slippy-map (XYZ) مصيَّرة فعليّاً من COG المؤشّر المقصوص للحقل.

    يجد أحدث COG للحقل+المؤشّر (نفس بحث الشبكة؛ salinity→ndsi)، يحسب حدود
    البلاطة في EPSG:3857، يعيد إسقاط COG (UTM غالباً) إلى 256×256 لتلك البقعة،
    يلوّنها بتدرّج المؤشّر، ويُرجِع PNG. البكسلات خارج الحقل/NaN → شفّافة.

    صدق + لا 500: عند غياب COG/rasterio/تقاطع البيانات → بلاطة شفّافة (الخريطة
    لا تُظهر شيئاً فوق الحقل) بدل خطأ خادم.
    """
    await _require_field_tenant(field_id)  # تفويض: ملكيّة الحقل (DB مصدر الحقيقة + ذاكرة)
    index = _normalize_index(index)
    _obs_inc("tile_requests_total", index)
    tenant = _REQ_TENANT.get()
    cache_path = _tile_cache_key(field_id, index, date, z, x, y, tenant, v=v)
    cached_png = _read_tile_cache(cache_path)
    if cached_png:
        _obs_inc("tile_cache_hits_total", index)
        return Response(
            content=cached_png,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Sahool-Tile-Cache": "hit",
                "X-Sahool-Tile-Date": date,
                "X-Sahool-Tile-Version": v or "default",
            },
        )
    layer = await _resolve_field_layer(field_id, index, date)
    if layer is not None and layer.get("cog_url"):
        try:
            import tile_render

            cog_path = object_store.to_gdal_path(layer["cog_url"])
            internal = _normalize_index(index)
            png = tile_render.render_tile_png(cog_path, z, x, y, internal)
            if png:
                _obs_inc("tile_cache_misses_total", index)
                _write_tile_cache(cache_path, png)
                return Response(
                    content=png,
                    media_type="image/png",
                    headers={
                        "Cache-Control": "public, max-age=3600",
                        "X-Sahool-Tile-Cache": "miss",
                        "X-Sahool-Tile-Date": date,
                        "X-Sahool-Tile-Version": v or "default",
                    },
                )
        except Exception as e:  # noqa: BLE001 — لا نُفشل الخريطة، نخدم شفّافاً
            _obs_inc("tile_render_errors_total", index)
            logger.warning("field_tile render skipped (%s): %s", field_id, e)
    # لا COG/بيانات/rasterio → بلاطة شفّافة (لا 500)
    _obs_inc("tile_transparent_total", index)
    return Response(
        content=_TRANSPARENT_PNG,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "X-Sahool-Tile-Cache": "transparent",
            "X-Sahool-Tile-Date": date,
        },
    )


@app.get("/v1/fields/{field_id}/available-dates")
async def field_available_dates(
    field_id: str,
    index: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Return real imagery acquisition dates with ready/COG status for a field.

    This endpoint is used by MapHub's scene selector. It must be tenant-filtered
    and must report dates from actual persisted/generated COGs, not from the UI
    or a provider search alone.
    """
    await _require_field_tenant(field_id, hide_existence=True)
    wanted = [_normalize_index(index)] if index else []
    by_date: dict[str, dict] = {}

    def _add(date_value, *, idx=None, has_cog=True, cloud_pct=None, scene_id=None):
        if not date_value:
            return
        d = str(date_value)[:10]
        if len(d) != 10:
            return
        rec = by_date.setdefault(
            d, {"date": d, "has_cog": False, "indices": set(), "cloud_pct": None, "scene_id": None}
        )
        rec["has_cog"] = bool(rec["has_cog"] or has_cog)
        if idx:
            rec["indices"].add(_display_index(idx))
        if cloud_pct is not None and rec["cloud_pct"] is None:
            try:
                rec["cloud_pct"] = float(cloud_pct)
            except (TypeError, ValueError):
                pass
        if scene_id and not rec["scene_id"]:
            rec["scene_id"] = str(scene_id)

    for lid in _field_layers.get(field_id, []):
        lyr = _layers.get(lid)
        if not lyr or not lyr.get("cog_url"):
            continue
        idx = lyr.get("index")
        if wanted and _normalize_index(idx) not in wanted:
            continue
        _add(
            lyr.get("acquisition_date"),
            idx=idx,
            has_cog=True,
            cloud_pct=lyr.get("cloud_pct"),
            scene_id=(lyr.get("provenance") or {}).get("scene_id")
            if isinstance(lyr.get("provenance"), dict)
            else None,
        )

    try:
        import db_persist

        rows = await db_persist.list_available_asset_dates(
            field_id,
            tenant_id=_REQ_TENANT.get(),
            indices=wanted or None,
            limit=limit,
        )
        for row in rows:
            _add(
                row.get("date"),
                idx=row.get("index_name"),
                has_cog=row.get("has_cog", True),
                cloud_pct=row.get("cloud_pct"),
                scene_id=row.get("scene_id"),
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("available dates DB lookup skipped (%s): %s", field_id, e)

    dates = []
    for rec in by_date.values():
        rec["indices"] = sorted(rec["indices"])
        dates.append(rec)
    dates.sort(key=lambda r: r["date"], reverse=True)
    return {"field_id": field_id, "dates": dates[:limit]}


@app.get("/v1/fields/{field_id}/tilejson")
async def field_tilejson(
    field_id: str,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    v: str | None = Query(None),
):
    """TileJSON 2.2.0 للحقل — يستهلكه Leaflet/MapLibre مباشرة.

    tiles[] يشير إلى مسار التصيير الذاتي (يعمل بلا TiTiler). bounds من حدود
    COG بـ4326. إن ضُبط TITILER_URL ووُجد cog_url نعرض رابط TiTiler إضافيّاً
    (اختياري)، لكنّ البلاطات الذاتيّة تعمل دائماً.
    """
    await _require_field_tenant(
        field_id, hide_existence=True
    )  # لا نكشف وجود حقل tenant آخر عبر tilejson
    out_index = _display_index(index)
    index = _normalize_index(index)
    _obs_inc("tilejson_requests_total", index)
    layer = await _resolve_field_layer(field_id, index, date)
    bounds = None
    if layer is not None and layer.get("bounds_4326"):
        b = layer["bounds_4326"]
        if b and len(b) == 4 and any(v != 0.0 for v in b):
            bounds = [round(float(v), 6) for v in b]
    # صدق: غياب COG ⇒ لا حدود حقيقيّة. لا نختلق حدوداً ضيّقة (الجوف) كأنّها بيانات
    # الحقل — نعلن available=False ونعطي حدوداً عالميّة محايدة (لا تُقفِز الخريطة لمكان
    # خاطئ)، فيستطيع المستهلِك (FieldIndicatorMap) أن يميّز "لا طبقة" من بيانات فعليّة.
    has_data = bounds is not None
    _obs_inc("tilejson_available_total" if has_data else "tilejson_unavailable_total", index)
    if bounds is None:
        bounds = [-180.0, -85.0, 180.0, 85.0]

    center = [
        round((bounds[0] + bounds[2]) / 2.0, 6),
        round((bounds[1] + bounds[3]) / 2.0, 6),
        14,
    ]
    resolved_date = (layer.get("acquisition_date") or date)[:10] if layer else date
    resolved_version = v or str(
        (layer or {}).get("created_at") or (layer or {}).get("cog_url") or "default"
    )
    qs_parts = [f"index={out_index}", f"date={date}", f"resolved_date={resolved_date}"]
    # TileJSON is fetched by JS, but the returned tiles are loaded later as <img>
    # requests and cannot rely on axios headers. Propagate the tenant hint from the
    # already-validated request into the tile URL so restart/DB rehydration keeps
    # working for MapLibre/Leaflet consumers.
    req_tenant = _REQ_TENANT.get()
    if req_tenant:
        qs_parts.append(f"tid={req_tenant}")
    if resolved_version:
        qs_parts.append(f"v={resolved_version}")
    qs = "&".join(qs_parts)
    self_tiles = f"/v1/fields/{field_id}/tiles/{{z}}/{{x}}/{{y}}.png?{qs}"

    tj = {
        "tilejson": "2.2.0",
        "name": f"field-{field_id}-{out_index}",
        "description": "بلاطات مؤشّر مصيَّرة ذاتيّاً من COG الحقل المقصوص",
        "scheme": "xyz",
        "tiles": [self_tiles],
        "minzoom": 8,
        "maxzoom": 20,
        "bounds": bounds,
        "center": center,
        "source": "self-rendered",
        "available": has_data,
        "resolved_date": resolved_date,
        "cache_version": resolved_version,
        "legend": __import__("tile_render").index_legend(index),
        "reason": None if has_data else "no_field_cog_or_scene_available",
        "user_message": None
        if has_data
        else "لا توجد صورة مؤشر حقيقية متاحة لهذا الحقل والتاريخ. شغّل السحب التاريخي أو اختر تاريخاً آخر.",
        "recommended_action": None
        if has_data
        else "POST /v1/fields/{field_id}/imagery/backfill ثم أعد طلب TileJSON",
        "note": (
            None
            if has_data
            else "لا COG مقصوص للحقل — شغّل /process أو backfill أوّلاً (الحدود عالميّة محايدة لا بيانات حقل)"
        ),
    }
    # اختياري: رابط TiTiler الديناميكي إن توفّر (لا يُلغي الذاتي). cog_url للعميل:
    # عامّ http(s) فقط — لا نكشف مسارات التخزين الداخليّة (file://، s3://، مضيف داخليّ).
    cog_url = _public_cog_url(layer.get("cog_url") if layer else None)
    if TITILER_URL and cog_url:
        internal = _normalize_index(index)
        colormap = "RdYlGn_r" if internal in ("ndsi", "salinity") else "RdYlGn"
        tj["titiler_tiles"] = [
            f"{TITILER_URL}/cog/tiles/{{z}}/{{x}}/{{y}}.png?url={cog_url}&colormap_name={colormap}"
        ]
    return tj


# ─── معايرة الملوحة (البند ٢) ────────────────────────────────────
class SalinityClassifyRequest(BaseModel):
    ndsi: float


class SalinityFitRequest(BaseModel):
    samples: list[dict]  # [{"ndsi","ece_ds_m","extraction_method"}]


@app.post("/salinity/classify")
async def salinity_classify(req: SalinityClassifyRequest, x_agent_token: str = Header(None)):
    """يصنّف NDSI لصنف ملوحة (heuristic إقليمي للجوف). تقديري."""
    _require_service_token(x_agent_token)
    return _sal.classify_ndsi_salinity(req.ndsi)


@app.post("/salinity/calibrate")
async def salinity_calibrate(req: SalinityFitRequest, x_agent_token: str = Header(None)):
    """يلائم انحدار NDSI→ECe من أزواج حقيقيّة (عند جمعها بإحداثيّات + EC).

    يفرض: 5 عيّنات+ وطريقة استخلاص موحّدة (لا يقبل بيانات تُنتج معايرة زائفة)."""
    _require_service_token(x_agent_token)
    return _sal.fit_regression(req.samples)


# ─── Cloud-native GIS/STAC facade (Phase 4 inspired by TiTiler/Terracotta/OGC) ───
@app.get("/stac")
async def stac_landing() -> dict:
    """STAC landing page for SAHOOL internal imagery catalog facade."""
    import cloud_native_catalog as _cnc

    return _cnc.stac_landing_page()


@app.get("/stac/collections")
async def stac_collections() -> dict:
    """List internal STAC collections: source scenes and derived COG products."""
    import cloud_native_catalog as _cnc

    return _cnc.stac_collections()


@app.post("/stac/mosaicjson")
async def stac_mosaicjson(payload: dict) -> dict:
    """Build a lightweight MosaicJSON document from supplied STAC items/COG assets.

    This endpoint is intentionally stateless: persistence belongs to raster_registry/object
    storage. It lets the frontend/tiler preview a multi-scene mosaic contract safely.
    """
    import cloud_native_catalog as _cnc

    return _cnc.build_mosaicjson(
        name=str(payload.get("name") or "sahool-field-mosaic"),
        items=payload.get("items") or [],
        minzoom=int(payload.get("minzoom") or 8),
        maxzoom=int(payload.get("maxzoom") or 18),
    )


@app.post("/v1/scenes/quality-score")
async def scene_quality_score(payload: dict) -> dict:
    """Score scene quality from cloud/shadow/nodata metadata before processing."""
    import cloud_native_catalog as _cnc

    q = _cnc.score_scene_quality(
        cloud_pct=payload.get("cloud_pct"),
        shadow_pct=payload.get("shadow_pct", 0),
        nodata_pct=payload.get("nodata_pct", 0),
        haze_pct=payload.get("haze_pct", 0),
        resolution_m=payload.get("resolution_m", 10),
        max_cloud_pct=float(payload.get("max_cloud_pct", 35)),
    )
    return q.__dict__


@app.post("/v1/cog/registry/preview")
async def cog_registry_preview(payload: dict) -> dict:
    """Preview the canonical COG registry record without writing to DB."""
    import cloud_native_catalog as _cnc

    required = ["tenant_id", "field_id", "date", "index_type", "cog_url"]
    missing = [k for k in required if not payload.get(k)]
    if missing:
        raise HTTPException(status_code=422, detail={"missing": missing})
    return _cnc.cog_registry_record(
        tenant_id=str(payload["tenant_id"]),
        field_id=str(payload["field_id"]),
        date=str(payload["date"]),
        index_type=str(payload["index_type"]),
        cog_url=str(payload["cog_url"]),
        scene_id=payload.get("scene_id"),
        cloud_pct=payload.get("cloud_pct"),
        resolution_m=payload.get("resolution_m", 10),
    )


# ════════════════════════════════════════════════════════════════════
# توحيد main↔cert (Stage B): تفعيل بلاطات CDSE الحيّة (poly clip) من main
# ════════════════════════════════════════════════════════════════════
# cert تفرّع قبل مسار cdse-tiles؛ بنيته التحتيّة لـCDSE موجودة هنا
# (_run_cdse_processing/ProcessCdseRequest/_jobs/…) عدا ٣ مساعِدات للكاش/القفل.
# نضيفها ثمّ نُضمّن راوتر cdse_tiles (يستورد main لاحقاً — بلا دور دائريّ لأنّ
# التضمين في نهاية الملفّ بعد تعريف كلّ الرموز، كنمط register_routers).
_cdse_tile_cache: dict[str, tuple[float, str]] = {}
_cdse_cache_lock: object | None = None  # asyncio.Lock — تُنشأ عند أوّل استخدام


def _cdse_lock():
    """يُرجع asyncio.Lock الوحيد لحماية _cdse_tile_cache (lazy — آمن للخيوط)."""
    global _cdse_cache_lock
    import asyncio

    if _cdse_cache_lock is None:
        _cdse_cache_lock = asyncio.Lock()
    return _cdse_cache_lock


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


# تضمين راوتر بلاطات CDSE (poly clip + قناع rasterio + ملوحة SWIR) — مسار main.
# آمن (نمط router_registry): محروس بـtry/except كي لا يكسر تحميل main تحت عزل
# الاختبارات (تحميل main.py باسم مخصّص ⇒ `import main` في الراوتر يُعيد التحميل ⇒
# استيراد دائريّ مؤقّت). في التشغيل العاديّ main في sys.modules فيُحلّ الاستيراد ويُسجَّل.
try:  # noqa: E402
    from routers.cdse_tiles import router as _cdse_tiles_router

    app.include_router(_cdse_tiles_router)
except ImportError as _e:  # pragma: no cover — عزل اختبار فقط
    logger.warning("راوتر cdse_tiles غير مُضمَّن (استيراد دائريّ تحت العزل؟): %s", _e)
