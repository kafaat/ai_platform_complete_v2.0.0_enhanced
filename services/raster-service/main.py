"""
raster-service (port 8001) — خدمة الصور الجوّية والراستر لـSAHOOL

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
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import band_math
import httpx
import object_store
import salinity_calibration as _sal
from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
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


class ProcessRequest(BaseModel):
    tenant_id: str
    field_id: str | None = None
    raster_url: str | None = None
    indicator: IndicatorKind
    source_format: SourceFormat
    bands: BandMapping
    clip_polygon_geojson: dict | None = None
    apply_cloud_mask: bool = True
    tiling_strategy: str = "pyramid"
    zoom_min: int = 10
    zoom_max: int = 18
    # provenance (#7): تثبيت المصدر لإعادة الإنتاج
    scene_id: str | None = None  # item_id من STAC search
    capture_datetime: str | None = None  # وقت التقاط القمر


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


# ─── حالة في الذاكرة (للإنتاج: Redis/DB) ──────────────────────────
_jobs: dict[str, dict] = {}
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
    yield
    logger.info("raster-service stopping")


app = FastAPI(title="SAHOOL Raster Service", version="9.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)


# ─── مسارات بحث الصور ─────────────────────────────────────────────
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

    result = ta.compute_slope_aspect(req.dem_url, req.pixel_size_m)
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
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.get("/readyz")
async def readyz():
    """يتحقّق من الوصول لـEarth Search."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{EARTH_SEARCH_URL}/")
            ok = r.status_code < 500
        return {
            "status": "ready" if ok else "degraded",
            "earth_search": "reachable" if ok else "unreachable",
        }
    except httpx.HTTPError:
        return {"status": "degraded", "earth_search": "unreachable"}


# ─── معالجة الراستر: الرفع ────────────────────────────────────────
UPLOAD_DIR = os.getenv("RASTER_UPLOAD_DIR", "/tmp/sahool_rasters")

# مصادقة خدمة-لخدمة: رفع الراستر يكتب ملفّات — منع إساءة التخزين/الحقن
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")


def _require_service_token(x_agent_token: str = Header(None)) -> None:
    if not AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — الرفع معطّل بأمان")
    if x_agent_token != AGENT_TOKEN:
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
        raise HTTPException(500, f"فشل الحفظ: {e}") from e
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
        raise HTTPException(500, f"فشل الحفظ: {e}") from e
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


def _persist_raster_asset(
    req: ProcessRequest, cog_url: str, meta: dict, bounds: list, stats: dict
) -> None:
    """يُدرج صفّاً في raster_assets (best-effort). يُغلّف كلّ خطأ.

    _run_processing يعمل في threadpool (مهمّة خلفيّة متزامنة) فلا حلقة
    أحداث في خيطه؛ لذا asyncio.run آمن هنا. غياب القاعدة (لا DATABASE_URL/
    لا جدول/لا شبكة) يُبتلع بصدق ولا يُفشل المعالجة.
    """
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
                provenance={"stats": {k: stats.get(k) for k in ("min", "max", "mean", "std")}},
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
    job = _jobs[job_id]
    job["status"] = JobStatus.processing
    job["started_at"] = datetime.now(UTC).isoformat()
    job["progress_pct"] = 10
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
        logger.info(f"job {job_id} completed → layer {layer_id}")
    except Exception as e:  # noqa: BLE001
        job["status"] = JobStatus.failed
        job["error_message"] = str(e)
        logger.error(f"job {job_id} failed: {e}")


def _run_batch_processing(job_id: str, req: BatchProcessRequest):
    """يحسب عدّة مؤشّرات من نفس المشهد في مهمّة واحدة (كفاءة I/O).

    صدق: يعالج كلّ مؤشّر فعليّاً ويسجّل نتيجته. التوفير الحقيقي يأتي من قراءة
    المشهد مرّة (في الإنتاج مع rasterio)؛ بنيويّاً نتتبّع الكلّ في job واحد مع
    عزل فشل كلّ مؤشّر (فشل واحد لا يُسقط الباقي).
    """
    job = _jobs[job_id]
    job["status"] = JobStatus.processing
    job["started_at"] = datetime.now(UTC).isoformat()
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
        _jobs[sub_job_id] = {
            "job_id": sub_job_id,
            "status": JobStatus.pending,
            "progress_pct": 0,
            "created_at": datetime.now(UTC).isoformat(),
        }
        try:
            _run_processing(sub_job_id, single)
            sj = _jobs[sub_job_id]
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
    logger.info("batch %s: %d نجح، %d فشل", job_id, len(results), len(failed))


def _process_pixels(req: ProcessRequest, layer_id: str):
    """المعالجة الفعليّة للبكسلات (تعمل عند توفّر rasterio). تُرجع
    (stats, bounds_4326, resolution_m, meta) حيث meta يحوي cog_url/cog_crs/
    srid/nodata. تطبّق القصّ على الحقل + قناع الغيوم + إعادة إسقاط الحدود."""
    import numpy as np
    import rasterio

    formula = _INDICATOR_FORMULAS[req.indicator.value]
    with rasterio.open(req.raster_url.replace("file://", "")) as src:
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

        def band(idx):
            """يقرأ نطاقاً كـfloat32 مع قصّ اختياري على مضلّع الحقل."""
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
            # حوّل nodata إلى NaN كي لا يلوّث حساب المؤشّر
            if src.nodata is not None:
                a = np.where(a == src.nodata, np.nan, a)
            a = np.where(a == nodata_val, np.nan, a)
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
            arr = (nir - red) / (nir + red)
        elif ind == "gndvi":
            arr = (nir - green) / (nir + green)
        elif ind == "msi":
            # Moisture Stress Index: SWIR1/NIR (أعلى = إجهاد مائي أكبر)
            arr = swir1 / nir
        elif ind == "ndwi":
            arr = (green - nir) / (green + nir)
        elif ind == "ndmi":
            arr = (nir - swir1) / (nir + swir1)
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
                _ndvi = (nir - red) / (nir + red)
                arr = si.compute_dbsi(green, swir1, _ndvi, np)
            elif ind == "ndsi":
                arr = si.compute_ndsi(red, nir, np)
            else:  # satvi
                arr = si.compute_satvi(red, swir1, swir2, np)
        else:  # fapar تقريب من ndvi
            ndvi = (nir - red) / (nir + red)
            arr = np.clip(1.24 * ndvi - 0.168, 0, 1)

        # ── (٢) قناع الغيوم (SCL) ─────────────────────────────────────
        # Sentinel-2 L2A: نطاق Scene Classification (SCL). أصناف الغيوم/
        # الظلال = {3 ظلّ غيمة, 8 غيمة متوسّطة الاحتمال, 9 عالية, 10 سيرس,
        # 11 ثلج}. نضع المؤشّر NaN عندها كي لا تفسد الإحصاء.
        if req.apply_cloud_mask and b.scl is not None:
            scl = band_raw(b.scl)
            if scl is not None and scl.shape == arr.shape:
                cloud_classes = np.isin(scl, [3, 8, 9, 10, 11])
                arr = np.where(cloud_classes, np.nan, arr)

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
                arr, cog_path, _out["transform"], crs=cog_crs, nodata=float("nan")
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
            "nodata": float("nan"),
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
    _jobs[job_id] = {
        "job_id": job_id,
        "status": JobStatus.pending,
        "progress_pct": 0,
        "created_at": datetime.now(UTC).isoformat(),
    }
    # معالجة في الخلفيّة — لا تحجب الطلب (مهمّ لقلب النظام تحت الحمل).
    background_tasks.add_task(_run_processing, job_id, req)
    j = _jobs[job_id]
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

    try:
        vrt_path, index_map = stac_vrt.build_band_vrt(req.band_hrefs)
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
    _jobs[job_id] = {
        "job_id": job_id,
        "status": JobStatus.pending,
        "progress_pct": 0,
        "created_at": datetime.now(UTC).isoformat(),
    }
    background_tasks.add_task(_run_processing, job_id, preq)
    return {
        "job_id": job_id,
        "status": JobStatus.pending,
        "bands": index_map,
        "raster_url": vrt_path,
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
    _jobs[job_id] = {
        "job_id": job_id,
        "status": JobStatus.pending,
        "progress_pct": 0,
        "created_at": datetime.now(UTC).isoformat(),
        "indicators": [i.value for i in req.indicators],
    }
    background_tasks.add_task(_run_batch_processing, job_id, req)
    return {
        "job_id": job_id,
        "status": JobStatus.pending,
        "indicators": [i.value for i in req.indicators],
        "note": "استعلم /jobs/{job_id} — batch_results + batch_failed عند الاكتمال",
    }


@app.get("/jobs/{job_id}")
async def job_status(job_id: str):
    """حالة المهمّة."""
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
async def job_result(job_id: str):
    """نتيجة المهمّة (بعد الاكتمال)."""
    j = _jobs.get(job_id)
    if not j:
        raise HTTPException(404, "مهمّة غير موجودة")
    if j["status"] != JobStatus.completed:
        raise HTTPException(409, f"المهمّة غير مكتملة (الحالة: {j['status']})")
    return j["result"]


@app.get("/info/{layer_id}")
async def raster_info(layer_id: str):
    """معلومات طبقة راستر معالَجة."""
    layer = _layers.get(layer_id)
    if not layer:
        raise HTTPException(404, "طبقة غير موجودة")
    return layer


# بلاطة شفّافة 1×1 (PNG) — عند غياب البلاطة الفعليّة (بلا rasterio)
# FIX: السلسلة السابقة كانت بطول فردي (137 خانة ⇒ 68.5 بايت) فيفشل
# bytes.fromhex عند الاستيراد ويتعطّل إقلاع الخدمة بالكامل. هذه بلاطة
# PNG شفّافة 1×1 صحيحة (68 بايت، CRC سليمة، مُولّدة عبر zlib).
_TRANSPARENT_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f"
    "15c4890000000b49444154789c6360000200000500017a5eab3f00000000"
    "49454e44ae426082"
)


@app.get("/tiles/{layer_id}/{z}/{x}/{y}.png")
async def get_tile(layer_id: str, z: int, x: int, y: int):
    """بلاطة خريطة لطبقة (MapLibre). عند توفّر البلاطات المُنتجة تُخدَم من
    القرص؛ وإلّا تُرجع بلاطة شفّافة (بنية صحيحة للعرض)."""
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
async def storage_stats():
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
async def list_offline_packs():
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
async def download_offline_pack(pack_name: str):
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
    if layer_id not in _layers:
        raise HTTPException(404, "طبقة غير موجودة")
    layer = _layers[layer_id]
    cog_url = layer.get("cog_url") or layer.get("raster_url")

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
# اسم مؤشّر الملوحة في الواجهة "salinity"؛ داخليّاً يُحسب كـNDSI.
_GRID_INDEX_ALIASES = {"salinity": "ndsi"}


def _find_field_layer(field_id: str, index: str, date: str) -> dict | None:
    """يجد أحدث طبقة (لها COG) لحقل+مؤشّر، اختياريّاً بتاريخ محدّد.

    date="latest" → أحدث طبقة؛ "YYYY-MM-DD" → مطابقة acquisition_date.
    يُرجِع سجلّ الطبقة أو None (لا COG حقيقي متاح).
    """
    layer_ids = _field_layers.get(field_id, [])
    internal = _GRID_INDEX_ALIASES.get(index, index)
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
        dated = [c for c in cands if (c.get("acquisition_date") or "").startswith(date)]
        if dated:
            cands = dated
    # أحدث حسب created_at
    cands.sort(key=lambda c: c.get("created_at") or "", reverse=True)
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

        internal = _GRID_INDEX_ALIASES.get(index, index)
        asset = await db_persist.fetch_latest_asset(field_id, internal, date)
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
            "acquisition_date": asset.get("acquisition_date"),
            "bounds_4326": asset.get("bounds_4326"),
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
    import indicator_grid as ig

    # تطبيع اسم المؤشّر المعروض (salinity مقبول للواجهة)
    out_index = index

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


class PrescriptionRequest(BaseModel):
    index: str = "ndvi"
    date: str = "latest"
    grid: int = Field(32, ge=2, le=256)
    n_zones: int = Field(3, ge=2, le=6)
    base_rate: float | None = None  # معدّل أساسي (سماد/بذار) لاشتقاق معدّل المناطق
    strategy: str = "compensate"  # compensate | protect


@app.post("/v1/fields/{field_id}/prescription")
async def field_prescription(field_id: str, req: PrescriptionRequest):
    """وصفة مناطق الإدارة (VRT) من شبكة المؤشّر — سدّ Sprint 5b.

    يبني شبكة المؤشّر للحقل (نفس مسار indicator-grid: COG حقيقي إن وُجد وإلّا
    محاكاة صادقة)، يقسّمها بالكوانتايل إلى n_zones مناطق أداء، ويشتقّ معدّلاً
    موصى به لكلّ منطقة إن مُرّر base_rate. يُرجِع المناطق + إحصاء كلّ منطقة
    (pixel_count, pct, value_range) + متوسّط/تباين الحقل.

    صدق: real_data ينعكس من مصدر الشبكة؛ المعدّلات إرشاديّة (قرار agronomic
    يحتاج تحقّقاً ميدانيّاً).
    """
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


# ─── بلاطات XYZ ديناميكيّة (TiTiler-style) من COG الحقل المقصوص ────────
@app.get("/v1/fields/{field_id}/tiles/{z}/{x}/{y}.png")
async def field_tile(
    field_id: str,
    z: int,
    x: int,
    y: int,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
):
    """بلاطة slippy-map (XYZ) مصيَّرة فعليّاً من COG المؤشّر المقصوص للحقل.

    يجد أحدث COG للحقل+المؤشّر (نفس بحث الشبكة؛ salinity→ndsi)، يحسب حدود
    البلاطة في EPSG:3857، يعيد إسقاط COG (UTM غالباً) إلى 256×256 لتلك البقعة،
    يلوّنها بتدرّج المؤشّر، ويُرجِع PNG. البكسلات خارج الحقل/NaN → شفّافة.

    صدق + لا 500: عند غياب COG/rasterio/تقاطع البيانات → بلاطة شفّافة (الخريطة
    لا تُظهر شيئاً فوق الحقل) بدل خطأ خادم.
    """
    layer = await _resolve_field_layer(field_id, index, date)
    if layer is not None and layer.get("cog_url"):
        try:
            import tile_render

            cog_path = object_store.to_gdal_path(layer["cog_url"])
            internal = _GRID_INDEX_ALIASES.get(index, index)
            png = tile_render.render_tile_png(cog_path, z, x, y, internal)
            if png:
                return Response(
                    content=png,
                    media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"},
                )
        except Exception as e:  # noqa: BLE001 — لا نُفشل الخريطة، نخدم شفّافاً
            logger.warning("field_tile render skipped (%s): %s", field_id, e)
    # لا COG/بيانات/rasterio → بلاطة شفّافة (لا 500)
    return Response(
        content=_TRANSPARENT_PNG,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=60"},
    )


@app.get("/v1/fields/{field_id}/tilejson")
async def field_tilejson(
    field_id: str,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
):
    """TileJSON 2.2.0 للحقل — يستهلكه Leaflet/MapLibre مباشرة.

    tiles[] يشير إلى مسار التصيير الذاتي (يعمل بلا TiTiler). bounds من حدود
    COG بـ4326. إن ضُبط TITILER_URL ووُجد cog_url نعرض رابط TiTiler إضافيّاً
    (اختياري)، لكنّ البلاطات الذاتيّة تعمل دائماً.
    """
    layer = await _resolve_field_layer(field_id, index, date)
    bounds = None
    if layer is not None and layer.get("bounds_4326"):
        b = layer["bounds_4326"]
        if b and len(b) == 4 and any(v != 0.0 for v in b):
            bounds = [round(float(v), 6) for v in b]
    if bounds is None:
        # حدود افتراضيّة (الجوف، اليمن) عند غياب COG — TileJSON يبقى صالحاً
        bounds = [44.0, 16.0, 44.01, 16.01]

    center = [
        round((bounds[0] + bounds[2]) / 2.0, 6),
        round((bounds[1] + bounds[3]) / 2.0, 6),
        14,
    ]
    qs = f"index={index}&date={date}"
    self_tiles = f"/v1/fields/{field_id}/tiles/{{z}}/{{x}}/{{y}}.png?{qs}"

    tj = {
        "tilejson": "2.2.0",
        "name": f"field-{field_id}-{index}",
        "description": "بلاطات مؤشّر مصيَّرة ذاتيّاً من COG الحقل المقصوص",
        "scheme": "xyz",
        "tiles": [self_tiles],
        "minzoom": 8,
        "maxzoom": 20,
        "bounds": bounds,
        "center": center,
        "source": "self-rendered",
    }
    # اختياري: رابط TiTiler الديناميكي إن توفّر (لا يُلغي الذاتي)
    cog_url = layer.get("cog_url") if layer else None
    if TITILER_URL and cog_url:
        internal = _GRID_INDEX_ALIASES.get(index, index)
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
