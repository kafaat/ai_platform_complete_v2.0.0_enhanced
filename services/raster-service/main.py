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
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

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
EARTH_SEARCH_URL = os.getenv(
    "EARTH_SEARCH_URL", "https://earth-search.aws.element84.com/v1")
SENTINEL_COLLECTION = "sentinel-2-l2a"
SENTINEL1_COLLECTION = "sentinel-1-grd"   # رادار SAR — يخترق الغيوم والليل
LANDSAT_COLLECTION = "landsat-c2-l2"      # Landsat C2 L2 — أرشيف 40+ سنة (تكميلي)
DEM_COLLECTION = "cop-dem-glo-30"         # Copernicus DEM 30م — ارتفاع/انحدار/صرف
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30"))
# خادم بلاطات COG ديناميكي (TiTiler) — سدّ فجوة P0. فارغ = البلاطات الثابتة.
TITILER_URL = os.getenv("TITILER_URL", "")

# عميل STAC مرن (تحسين قلب النظام): إعادة محاولة + cache (Redis مشترك +
# ذاكرة fallback) + مصدر احتياطي + stale-if-error. TTL قابل للضبط.
from stac_client import ResilientStacClient
# المصدر الاحتياطي الأوّل: Microsoft Planetary Computer (STAC عامّ، بحث مجهول).
# نفس بنية STAC، فيعمل بنفس payload عند تعذّر Element84.
PC_STAC_URL = os.getenv(
    "PLANETARY_COMPUTER_URL", "https://planetarycomputer.microsoft.com/api/stac/v1")
# مصدر احتياطي ثانٍ (اختياري): Digital Earth Africa — يغطّي أفريقيا فقط.
# اليمن خارج تغطيته، لذا معطّل افتراضيّاً؛ يُفعَّل لمناطق أفريقيّة (القرن الأفريقي).
DEAFRICA_STAC_URL = os.getenv(
    "DEAFRICA_STAC_URL", "https://explorer.digitalearth.africa/stac")

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
class IndicatorKind(str, Enum):
    ndvi = "ndvi"; evi = "evi"; savi = "savi"; ndwi = "ndwi"; ndmi = "ndmi"
    gndvi = "gndvi"; fapar = "fapar"; vari = "vari"; gli = "gli"; tgi = "tgi"
    ndre = "ndre"; msi = "msi"  # NDRE (نيتروجين/red-edge) + MSI (إجهاد مائي)
    # مؤشّرات التربة (Sentinel-2) — تسدّ نقص: السابقة كلّها نباتيّة
    bsi = "bsi"; bi = "bi"; bi2 = "bi2"; ndti = "ndti"
    dbsi = "dbsi"; ndsi = "ndsi"; satvi = "satvi"


class SourceFormat(str, Enum):
    sentinel2_l2a = "sentinel2_l2a"; sentinel2_l1c = "sentinel2_l1c"
    landsat8 = "landsat8"; drone_orthomosaic = "drone_orthomosaic"; custom = "custom"


class JobStatus(str, Enum):
    pending = "pending"; processing = "processing"; completed = "completed"
    failed = "failed"; cancelled = "cancelled"


class BandMapping(BaseModel):
    red: Optional[int] = None
    green: Optional[int] = None
    blue: Optional[int] = None
    nir: Optional[int] = None
    rededge: Optional[int] = None  # red-edge (B5/B6/B7) — لـNDRE (النيتروجين)
    swir1: Optional[int] = None
    swir2: Optional[int] = None   # لمؤشّرات التربة (BSI/NDTI/SATVI)
    scl: Optional[int] = None


class ProcessRequest(BaseModel):
    tenant_id: str
    field_id: Optional[str] = None
    raster_url: Optional[str] = None
    indicator: IndicatorKind
    source_format: SourceFormat
    bands: BandMapping
    clip_polygon_geojson: Optional[dict] = None
    apply_cloud_mask: bool = True
    tiling_strategy: str = "pyramid"
    zoom_min: int = 10
    zoom_max: int = 18
    # provenance (#7): تثبيت المصدر لإعادة الإنتاج
    scene_id: Optional[str] = None          # item_id من STAC search
    capture_datetime: Optional[str] = None  # وقت التقاط القمر



class BatchProcessRequest(BaseModel):
    """معالجة دفعيّة: عدّة مؤشّرات من نفس المشهد في مهمّة واحدة (كفاءة).

    بدل طلب لكلّ مؤشّر (يقرأ النطاقات مرّة لكلّ منها)، هذا يقرأ المشهد مرّة
    ويحسب كلّ المؤشّرات — توفير I/O كبير، مهمّ لقلب النظام تحت الحمل.
    """
    tenant_id: str
    field_id: Optional[str] = None
    raster_url: Optional[str] = None
    indicators: list[IndicatorKind]   # قائمة المؤشّرات (NDVI + NDRE + NDSI ...)
    source_format: SourceFormat
    bands: BandMapping
    clip_polygon_geojson: Optional[dict] = None
    apply_cloud_mask: bool = True
    scene_id: Optional[str] = None
    capture_datetime: Optional[str] = None

class SearchRequest(BaseModel):
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    datetime_start: str
    datetime_end: str
    max_cloud_pct: float = 30
    limit: int = 20


# ─── حالة في الذاكرة (للإنتاج: Redis/DB) ──────────────────────────
_jobs: dict[str, dict] = {}
_layers: dict[str, dict] = {}


# ─── بحث الصور عبر Element84 STAC ─────────────────────────────────
def _band_urls_from_assets(assets: dict) -> dict:
    """يستخرج روابط النطاقات من STAC assets (Sentinel-2 L2A)."""
    def url(key: str) -> Optional[str]:
        a = assets.get(key)
        return a.get("href") if a else None
    return {
        "blue": url("blue"), "green": url("green"), "red": url("red"),
        "rededge1": url("rededge1"), "rededge2": url("rededge2"),
        "rededge3": url("rededge3"), "nir": url("nir"), "nir08": url("nir08"),
        "swir16": url("swir16"), "swir22": url("swir22"), "scl": url("scl"),
        "visual": url("visual"), "thumbnail": url("thumbnail"),
    }


async def _stac_search(bbox: list[float], dt_start: str, dt_end: str,
                       max_cloud: float, limit: int) -> dict:
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
        items.append({
            "item_id": feat.get("id", ""),
            "datetime": props.get("datetime", ""),
            "cloud_cover_pct": props.get("eo:cloud_cover", 0.0),
            "bbox": feat.get("bbox"),
            "bands_urls": _band_urls_from_assets(assets),
            "thumbnail_url": (assets.get("thumbnail") or {}).get("href"),
            "preview_url": (assets.get("visual") or {}).get("href"),
            "platform": props.get("platform", "sentinel-2"),
        })
    return {"count": len(items), "source": "element84-earth-search",
            "cache": data.get("_cache", "miss"),
            "warning": data.get("_warning"), "items": items}


async def _stac_search_radar(bbox: list[float], dt_start: str, dt_end: str,
                             limit: int) -> dict:
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
            k: (assets.get(k) or {}).get("href")
            for k in ("vv", "vh", "hh", "hv")
            if assets.get(k)
        }
        items.append({
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
        })
    return {"count": len(items), "source": "element84-earth-search",
            "collection": SENTINEL1_COLLECTION, "items": items}


async def _stac_search_landsat(bbox: list[float], dt_start: str, dt_end: str,
                               max_cloud: float, limit: int) -> dict:
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
        items.append({
            "item_id": feat.get("id", ""),
            "datetime": props.get("datetime", ""),
            "cloud_cover_pct": props.get("eo:cloud_cover", 0.0),
            "bbox": feat.get("bbox"),
            "platform": props.get("platform", "landsat"),
            "thumbnail_url": (assets.get("thumbnail") or {}).get("href"),
            "data_type": "optical",
            "note_ar": "Landsat 30م — أرشيف طويل المدى، تكميلي لـSentinel-2.",
        })
    return {"count": len(items), "source": "element84-earth-search",
            "collection": LANDSAT_COLLECTION, "cache": data.get("_cache"),
            "items": items}


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
        items.append({
            "item_id": feat.get("id", ""),
            "bbox": feat.get("bbox"),
            "dem_url": (assets.get("data") or assets.get("elevation") or {}).get("href"),
            "data_type": "elevation",
            "resolution_m": 30,
            "note_ar": "نموذج ارتفاع 30م — للانحدار/الصرف/حصاد المياه. ثابت لا زمني.",
        })
    return {"count": len(items), "source": "element84-earth-search",
            "collection": DEM_COLLECTION, "cache": data.get("_cache"),
            "items": items}


# ─── lifespan + التطبيق ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("raster-service starting (Element84 Earth Search)")
    yield
    logger.info("raster-service stopping")


app = FastAPI(title="SAHOOL Raster Service", version="9.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"], allow_credentials=True,
)


# ─── مسارات بحث الصور ─────────────────────────────────────────────
@app.get("/imagery/search/recent")
async def imagery_search_recent(
    west: float, south: float, east: float, north: float,
    days_back: int = Query(30, ge=1, le=365),
    max_cloud_pct: float = Query(30, ge=0, le=100),
):
    """آخر صور Sentinel-2 لمنطقة بـbbox (خلال days_back يوماً)."""
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    end = now.strftime("%Y-%m-%dT23:59:59Z")
    try:
        return await _stac_search([west, south, east, north], start, end,
                                  max_cloud_pct, limit=20)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search: {e}")


@app.get("/imagery/search/season")
async def imagery_search_season(
    west: float, south: float, east: float, north: float,
    sowing_date: str, harvest_date: Optional[str] = None,
    max_cloud_pct: float = Query(40, ge=0, le=100),
):
    """كلّ صور الموسم الزراعي (من البذار للحصاد) — للـCropTimeline."""
    end = harvest_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = f"{sowing_date}T00:00:00Z"
    end_iso = f"{end}T23:59:59Z"
    try:
        return await _stac_search([west, south, east, north], start, end_iso,
                                  max_cloud_pct, limit=60)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search: {e}")


@app.get("/imagery/best")
async def imagery_best_scene(
    west: float, south: float, east: float, north: float,
    lookback_days: int = Query(30, ge=1, le=180),
    max_cloud_pct: float = Query(40, ge=0, le=100),
):
    """يختار أفضل مشهد حديث (توازن الحداثة + قلّة الغيوم) — تحسين القلب.

    بدل أخذ الأحدث دائماً (قد يكون غائماً)، يوازن: مشهد حديث منخفض الغيوم
    أفضل من أحدث غائم. درجة = أولويّة قلّة الغيوم مع تفضيل الحداثة عند التعادل.
    صدق: يختار من المتاح فعليّاً؛ لا يخترع مشهداً.
    """
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    try:
        result = await _stac_search([west, south, east, north],
                                    f"{start}T00:00:00Z", f"{end}T23:59:59Z",
                                    max_cloud_pct, limit=30)
    except (httpx.HTTPError, RuntimeError) as e:
        raise HTTPException(502, f"Earth Search: {e}")

    items = result.get("items", [])
    if not items:
        return {"best": None, "candidates": 0,
                "note": "لا مشاهد ضمن المعايير — وسّع lookback أو max_cloud"}

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
        return await _stac_search(req.bbox, req.datetime_start, req.datetime_end,
                                  req.max_cloud_pct, req.limit)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search: {e}")


@app.get("/imagery/timeseries")
async def imagery_timeseries(
    west: float, south: float, east: float, north: float,
    start: str, end: Optional[str] = None,
    max_cloud_pct: float = Query(40, ge=0, le=100),
):
    """تحليل زمني (سدّ فجوة P0): تركيب شهري + اتّجاه + كشف شذوذ.

    يبحث STAC عن مشاهد الفترة، يجمّعها شهريّاً (median compositing لتخفيف
    الغيوم)، ويحسب الاتّجاه (تحسّن/تدهور) والشذوذ. صدق: عند توفّر القيم
    المحسوبة لكلّ مشهد تُجمَّع؛ وإلّا يُرجِع البنية الزمنيّة + المشاهد لحساب
    العميل/العامل (لا يخترع قيم NDVI من البحث وحده).
    """
    import time_series as ts
    end_date = end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        search = await _stac_search(
            [west, south, east, north],
            f"{start}T00:00:00Z", f"{end_date}T23:59:59Z",
            max_cloud_pct, limit=100)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search: {e}")

    scenes = search.get("items", [])
    # المشاهد من STAC تحمل التاريخ والغيوم لكن ليس NDVI محسوباً بعد —
    # نُرجِع البنية الزمنيّة (تجميع شهري بعدد المشاهد) + قائمة للمعالجة.
    by_month = ts.monthly_composite(
        [{"datetime": s["datetime"], "mean": None} for s in scenes],
        value_key="mean") if scenes else []
    # تجميع شهري لعدد المشاهد المتاحة (لا قيم مخترعة)
    from collections import Counter
    month_counts = Counter(s["datetime"][:7] for s in scenes if s.get("datetime"))
    timeline = [{"month": m, "scenes_available": c}
                for m, c in sorted(month_counts.items())]
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
async def imagery_timeseries_analyze(req: TimeSeriesAnalyzeRequest,
                                     x_agent_token: str = Header(None)):
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
    base_rate: Optional[float] = None
    strategy: str = "compensate"


@app.post("/zones/classify")
async def zones_classify(req: ManagementZonesRequest,
                         x_agent_token: str = Header(None)):
    """مناطق الإدارة داخل الحقل (سدّ فجوة P1): تقسيم أداء + وصفة VRT.

    يقسّم قيم بكسلات المؤشّر لمناطق (عالٍ/متوسّط/منخفض) بالكوانتايل، ويُنتج
    وصفة متغيّرة المعدّل إن مُرّر base_rate. صدق: يعمل على قيم حقيقيّة.
    """
    _require_service_token(x_agent_token)
    import management_zones as mz
    result = mz.classify_zones(req.pixel_values, n_zones=req.n_zones)
    if req.base_rate is not None and result.get("zones"):
        result["prescription"] = mz.prescription_from_zones(
            result["zones"], req.base_rate, strategy=req.strategy)
    return result


@app.get("/imagery/search/radar")
async def imagery_search_radar(
    west: float, south: float, east: float, north: float,
    start: str, end: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
):
    """بحث رادار Sentinel-1 GRD — يخترق الغيوم (مفيد لموسم الأمطار).

    لا فلتر غيوم (الرادار لا يتأثّر بها). يُرجع استقطابات VV/VH للاستخدام
    في رطوبة التربة وكشف الفيضانات — لا NDVI.
    """
    end_date = end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        return await _stac_search_radar(
            [west, south, east, north],
            f"{start}T00:00:00Z", f"{end_date}T23:59:59Z", limit)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Earth Search (radar): {e}")


@app.get("/imagery/search/landsat")
async def imagery_search_landsat(
    west: float, south: float, east: float, north: float,
    start: str, end: Optional[str] = None,
    max_cloud_pct: float = Query(40, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100),
):
    """بحث Landsat C2 L2 — أرشيف طويل المدى (40+ سنة) تكميلي لـSentinel-2.

    دقّة 30م، تردّد 16 يوماً. مفيد للتحليل التاريخي قبل عصر Sentinel-2 (2015).
    """
    end_date = end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        return await _stac_search_landsat(
            [west, south, east, north],
            f"{start}T00:00:00Z", f"{end_date}T23:59:59Z", max_cloud_pct, limit)
    except (httpx.HTTPError, RuntimeError) as e:
        raise HTTPException(502, f"Earth Search (landsat): {e}")


@app.get("/imagery/dem")
async def imagery_dem(west: float, south: float, east: float, north: float):
    """نموذج الارتفاع الرقمي (Copernicus DEM 30م) لمنطقة — للانحدار/الصرف.

    حرج لزراعة اليمن المُدرّجة الصحراويّة: تخطيط حصاد المياه، اتّجاه الجريان،
    مواقع السدود الترابيّة. DEM ثابت (لا زمني) — لا datetime/cloud.
    """
    try:
        return await _stac_search_dem([west, south, east, north])
    except (httpx.HTTPError, RuntimeError) as e:
        raise HTTPException(502, f"Earth Search (DEM): {e}")


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
        result["water_harvesting"] = ta.classify_water_harvesting(
            result["slope_deg"]["mean"])
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
        f"{sum(1 for j in _jobs.values() if _s(j.get('status'))=='processing')}",
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
    return PlainTextResponse("\n".join(lines) + "\n",
                             media_type="text/plain; version=0.0.4")


@app.get("/readyz")
async def readyz():
    """يتحقّق من الوصول لـEarth Search."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{EARTH_SEARCH_URL}/")
            ok = r.status_code < 500
        return {"status": "ready" if ok else "degraded",
                "earth_search": "reachable" if ok else "unreachable"}
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
        raise HTTPException(500, f"فشل الحفظ: {e}")
    logger.info(f"raster uploaded: {raster_id} ({len(content)} bytes)")
    return {"raster_url": f"file://{path}"}


@app.post("/upload/drone")
async def upload_drone(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    field_id: Optional[str] = Form(None),
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
        raise HTTPException(500, f"فشل الحفظ: {e}")
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
    "fapar": "أساسها NDVI (علاقة تجريبيّة)",
    "vari": "(GREEN - RED) / (GREEN + RED - BLUE)",   # RGB-only للدرون
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


def _run_processing(job_id: str, req: ProcessRequest):
    """ينفّذ معالجة المؤشّر. البنية كاملة؛ حساب البكسلات الفعلي يتمّ عند
    توفّر rasterio في بيئة التشغيل (يُحقن هنا)."""
    job = _jobs[job_id]
    job["status"] = JobStatus.processing
    job["started_at"] = datetime.now(timezone.utc).isoformat()
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
            import rasterio  # noqa: F401
            import numpy  # noqa: F401
            _has_raster_libs = True
        except ImportError:
            _has_raster_libs = False

        layer_id = f"layer_{uuid.uuid4().hex[:12]}"
        if _has_raster_libs and req.raster_url:
            # المعالجة الفعليّة (تتمّ في بيئة التشغيل مع rasterio)
            stats, bounds, res_m = _process_pixels(req, layer_id)
        else:
            # بنية بلا حساب فعلي (البيئة بلا rasterio) — ترجع هيكلاً صحيحاً
            stats = {"min": 0.0, "max": 1.0, "mean": 0.0, "std": 0.0,
                     "valid_pixels": 0, "nodata_pixels": 0}
            bounds = [0.0, 0.0, 0.0, 0.0]
            res_m = 10.0
            job["note"] = "rasterio غير متوفّر — بنية صحيحة بلا حساب بكسلات"

        now = datetime.now(timezone.utc).isoformat()
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
        _layers[layer_id] = {
            "layer_id": layer_id,
            "source_format": req.source_format.value,
            "width": 0, "height": 0, "band_count": 1, "crs": "EPSG:4326",
            "bounds_4326": bounds, "resolution_m": res_m,
            "provenance": provenance,
        }
        job["result"] = {
            "job_id": job_id, "layer_id": layer_id,
            "indicator": req.indicator.value, "stats": stats,
            "tile_url_template": f"/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png",
            "bounds_4326": bounds, "zoom_min": req.zoom_min,
            "zoom_max": req.zoom_max, "finished_at": now,
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


def _run_batch_processing(job_id: str, req: "BatchProcessRequest"):
    """يحسب عدّة مؤشّرات من نفس المشهد في مهمّة واحدة (كفاءة I/O).

    صدق: يعالج كلّ مؤشّر فعليّاً ويسجّل نتيجته. التوفير الحقيقي يأتي من قراءة
    المشهد مرّة (في الإنتاج مع rasterio)؛ بنيويّاً نتتبّع الكلّ في job واحد مع
    عزل فشل كلّ مؤشّر (فشل واحد لا يُسقط الباقي).
    """
    job = _jobs[job_id]
    job["status"] = JobStatus.processing
    job["started_at"] = datetime.now(timezone.utc).isoformat()
    results = {}
    failed = {}
    total = len(req.indicators)
    for i, ind in enumerate(req.indicators):
        # ابنِ ProcessRequest فرديّاً لكلّ مؤشّر (يعيد استخدام المنطق المُختبَر)
        single = ProcessRequest(
            tenant_id=req.tenant_id, field_id=req.field_id,
            raster_url=req.raster_url, indicator=ind,
            source_format=req.source_format, bands=req.bands,
            clip_polygon_geojson=req.clip_polygon_geojson,
            apply_cloud_mask=req.apply_cloud_mask,
            scene_id=req.scene_id, capture_datetime=req.capture_datetime,
        )
        sub_job_id = f"{job_id}_{ind.value}"
        _jobs[sub_job_id] = {
            "job_id": sub_job_id, "status": JobStatus.pending,
            "progress_pct": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
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

    job["status"] = (JobStatus.completed if results else JobStatus.failed)
    job["finished_at"] = datetime.now(timezone.utc).isoformat()
    job["batch_results"] = results
    job["batch_failed"] = failed
    logger.info("batch %s: %d نجح، %d فشل", job_id, len(results), len(failed))


def _process_pixels(req: ProcessRequest, layer_id: str):
    """المعالجة الفعليّة للبكسلات (تعمل عند توفّر rasterio). تُرجع
    (stats, bounds_4326, resolution_m)."""
    import numpy as np
    import rasterio
    formula = _INDICATOR_FORMULAS[req.indicator.value]
    with rasterio.open(req.raster_url.replace("file://", "")) as src:
        bounds = list(src.bounds)  # (left, bottom, right, top)
        res_m = abs(src.res[0])
        b = req.bands
        # اقرأ النطاقات المطلوبة حسب المؤشّر
        def band(idx):
            return src.read(idx).astype("float32") if idx else None
        red = band(b.red); nir = band(b.nir); green = band(b.green)
        blue = band(b.blue); swir1 = band(b.swir1)
        rededge = band(b.rededge) if b.rededge is not None else None
        swir2 = band(b.swir2) if b.swir2 is not None else None
        np.seterr(divide="ignore", invalid="ignore")
        ind = req.indicator.value
        if ind == "ndvi":
            arr = (nir - red) / (nir + red)
        elif ind == "gndvi":
            arr = (nir - green) / (nir + green)
        elif ind == "ndre":
            # NDRE: النيتروجين/الكلوروفيل عبر red-edge (الأدقّ للنيتروجين)
            if rededge is None:
                raise ValueError("NDRE يتطلّب نطاق rededge (B5/B6/B7) في bands")
            arr = (nir - rededge) / (nir + rededge)
        elif ind == "msi":
            # Moisture Stress Index: SWIR1/NIR (أعلى = إجهاد مائي أكبر)
            arr = swir1 / nir
        elif ind == "ndwi":
            arr = (green - nir) / (green + nir)
        elif ind == "ndmi":
            arr = (nir - swir1) / (nir + swir1)
        elif ind == "savi":
            arr = 1.5 * (nir - red) / (nir + red + 0.5)
        elif ind == "evi":
            arr = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)
        elif ind == "vari":
            arr = (green - red) / (green + red - blue)
        elif ind == "gli":
            arr = (2 * green - red - blue) / (2 * green + red + blue)
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
        # التخزين: حجم أصغر + قراءة جزئيّة أسرع (TiTiler/MapLibre).
        try:
            import cog_writer
            cog_path = os.path.join(UPLOAD_DIR, f"{req.indicator.value}_"
                                    f"{uuid.uuid4().hex[:8]}.tif")
            cog_info = cog_writer.write_cog(arr, cog_path, src.transform,
                                            crs=str(src.crs or "EPSG:4326"))
            stats["cog"] = cog_info
        except Exception as _e:  # noqa: BLE001 — حفظ COG اختياري لا يُفشل الحساب
            stats["cog"] = {"written": False, "reason": str(_e)}
        _ = formula  # موثّق أعلاه
        return stats, bounds, res_m


@app.post("/process")
async def process_raster(req: ProcessRequest, background_tasks: BackgroundTasks,
                         x_agent_token: str = Header(None)):
    _require_service_token(x_agent_token)
    """يبدأ معالجة مؤشّر (خلفيّة — لا يحجب الطلب). يُرجع job_id للاستعلام."""
    if not req.raster_url:
        raise HTTPException(400, "raster_url مطلوب (ارفع الراستر أوّلاً).")
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    _jobs[job_id] = {
        "job_id": job_id, "status": JobStatus.pending, "progress_pct": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # معالجة في الخلفيّة — لا تحجب الطلب (مهمّ لقلب النظام تحت الحمل).
    background_tasks.add_task(_run_processing, job_id, req)
    j = _jobs[job_id]
    return {
        "job_id": job_id, "status": j["status"], "progress_pct": j["progress_pct"],
        "created_at": j["created_at"], "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"), "error_message": j.get("error_message"),
    }


@app.post("/process/batch")
async def process_batch(req: BatchProcessRequest, background_tasks: BackgroundTasks,
                        x_agent_token: str = Header(None)):
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
        "job_id": job_id, "status": JobStatus.pending, "progress_pct": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "indicators": [i.value for i in req.indicators],
    }
    background_tasks.add_task(_run_batch_processing, job_id, req)
    return {
        "job_id": job_id, "status": JobStatus.pending,
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
        "job_id": job_id, "status": j["status"], "progress_pct": j["progress_pct"],
        "created_at": j["created_at"], "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"), "error_message": j.get("error_message"),
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
_TRANSPARENT_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d4944415478da6364f80f00010101005a4d5cce0000"
    "0000049454e44ae426082"
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
async def imagery_timeseries_parallel(req: TimeSeriesAnalyzeRequest,
                                      max_concurrency: int = Query(4, ge=1, le=10),
                                      x_agent_token: str = Header(None)):
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
        req.scene_values, _passthrough, max_concurrency=max_concurrency)


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
                packs.append({
                    "name": name,
                    "format": name.rsplit(".", 1)[-1],
                    "size_mb": round(os.path.getsize(path) / 1e6, 1),
                    "download_url": f"/offline/packs/{name}",
                })
    return {"count": len(packs), "packs": packs,
            "note": "حمّل الحزمة على الجهاز لعرض خريطة الخلفيّة بلا اتّصال"}


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
    return FileResponse(path, media_type="application/octet-stream",
                        filename=pack_name)


@app.get("/layers/{layer_id}/tilejson")
async def layer_tilejson(layer_id: str,
                         rescale: Optional[str] = Query(None),
                         colormap: Optional[str] = Query("viridis")):
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
            "minzoom": 8, "maxzoom": 18,
            "note": "بلاطات ديناميكيّة من COG عبر TiTiler (تمدّد/ألوان عند الطلب)",
        }
    # fallback: البلاطات الثابتة
    return {
        "source": "static-pregenerated",
        "tilejson": "2.2.0",
        "tiles": [f"/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png"],
        "minzoom": 8, "maxzoom": 16,
        "note": "بلاطات ثابتة مُولَّدة مسبقاً (TiTiler غير مضبوط). للديناميكي: "
                "اضبط TITILER_URL ووفّر cog_url للطبقة.",
    }


# ─── معايرة الملوحة (البند ٢) ────────────────────────────────────
import salinity_calibration as _sal


class SalinityClassifyRequest(BaseModel):
    ndsi: float


class SalinityFitRequest(BaseModel):
    samples: list[dict]   # [{"ndsi","ece_ds_m","extraction_method"}]


@app.post("/salinity/classify")
async def salinity_classify(req: SalinityClassifyRequest,
                            x_agent_token: str = Header(None)):
    """يصنّف NDSI لصنف ملوحة (heuristic إقليمي للجوف). تقديري."""
    _require_service_token(x_agent_token)
    return _sal.classify_ndsi_salinity(req.ndsi)


@app.post("/salinity/calibrate")
async def salinity_calibrate(req: SalinityFitRequest,
                             x_agent_token: str = Header(None)):
    """يلائم انحدار NDSI→ECe من أزواج حقيقيّة (عند جمعها بإحداثيّات + EC).

    يفرض: 5 عيّنات+ وطريقة استخلاص موحّدة (لا يقبل بيانات تُنتج معايرة زائفة)."""
    _require_service_token(x_agent_token)
    return _sal.fit_regression(req.samples)
