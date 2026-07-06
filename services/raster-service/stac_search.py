"""STAC search helpers for raster-service.

This module keeps external catalogue lookup and STAC payload shaping out of
``main.py`` while preserving the public helper names re-exported by ``main``.
The module is configured by ``main`` at startup/import time so it can reuse the
existing resilient STAC client, logger, and environment-derived constants without
creating a second client or changing runtime behaviour.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException

_stac: Any = None
_logger: Any = None
EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1"
HTTP_TIMEOUT = 30.0
HISTORICAL_SEARCH_PROVIDER = "cdse"
SENTINEL_COLLECTION = "sentinel-2-l2a"
SENTINEL1_COLLECTION = "sentinel-1-grd"
LANDSAT_COLLECTION = "landsat-c2-l2"
DEM_COLLECTION = "cop-dem-glo-30"
LANDSAT_UNIQUE_INDICES = {"lst", "cwsi", "tvdi", "tci", "vhi", "et_inputs"}
LANDSAT_DIRECT_RASTER_INDICES = {"lst"}
LANDSAT_DERIVED_INDICES = {"cwsi", "tvdi", "tci", "vhi", "et_inputs"}
LANDSAT_DUPLICATE_SENTINEL_INDICES = set()
LANDSAT_THERMAL_ASSET_CANDIDATES = (
    "lwir11",
    "surface_temperature",
    "st",
    "st_b10",
    "tir",
    "thermal",
    "thermal_ir",
)


def configure(
    *,
    stac: Any,
    logger: Any,
    earth_search_url: str,
    http_timeout: float,
    historical_search_provider: str,
    sentinel_collection: str,
    sentinel1_collection: str,
    landsat_collection: str,
    dem_collection: str,
    landsat_unique_indices: set[str],
    landsat_direct_raster_indices: set[str],
    landsat_derived_indices: set[str],
    landsat_duplicate_sentinel_indices: set[str],
    landsat_thermal_asset_candidates: tuple[str, ...],
) -> None:
    """Inject runtime dependencies owned by ``main.py``.

    Keeping configuration explicit avoids importing ``main`` from here, which
    would create a circular import for routers/tests that still import helpers
    through ``main``.
    """

    global _stac, _logger
    global EARTH_SEARCH_URL, HTTP_TIMEOUT, HISTORICAL_SEARCH_PROVIDER
    global SENTINEL_COLLECTION, SENTINEL1_COLLECTION, LANDSAT_COLLECTION, DEM_COLLECTION
    global LANDSAT_UNIQUE_INDICES, LANDSAT_DIRECT_RASTER_INDICES, LANDSAT_DERIVED_INDICES
    global LANDSAT_DUPLICATE_SENTINEL_INDICES, LANDSAT_THERMAL_ASSET_CANDIDATES

    _stac = stac
    _logger = logger
    EARTH_SEARCH_URL = earth_search_url
    HTTP_TIMEOUT = http_timeout
    HISTORICAL_SEARCH_PROVIDER = historical_search_provider
    SENTINEL_COLLECTION = sentinel_collection
    SENTINEL1_COLLECTION = sentinel1_collection
    LANDSAT_COLLECTION = landsat_collection
    DEM_COLLECTION = dem_collection
    LANDSAT_UNIQUE_INDICES = landsat_unique_indices
    LANDSAT_DIRECT_RASTER_INDICES = landsat_direct_raster_indices
    LANDSAT_DERIVED_INDICES = landsat_derived_indices
    LANDSAT_DUPLICATE_SENTINEL_INDICES = landsat_duplicate_sentinel_indices
    LANDSAT_THERMAL_ASSET_CANDIDATES = landsat_thermal_asset_candidates


def stac_health() -> dict:
    """Return the configured resilient STAC client health counters."""
    if _stac is None:
        return {
            "requests": 0,
            "cache_hit_rate": 0.0,
            "failures": 0,
            "stale_served": 0,
            "fallback_served": 0,
        }
    return _stac.health()


def band_urls_from_assets(assets: dict) -> dict:
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
        asset = assets.get(key)
        return asset.get("href") if asset else None

    return {
        "blue": url("blue"),
        "green": url("green"),
        "red": url("red"),
        "nir": url("nir"),
        "rededge": url("rededge1"),  # B05 → BandMapping.rededge (NDRE / red-edge)
        "swir1": url("swir16"),  # B11 → BandMapping.swir1   (NDMI / MSI / BSI)
        "swir2": url("swir22"),  # B12 → BandMapping.swir2   (BSI / SATVI / NDTI)
        "scl": url("scl"),
    }


async def stac_query(payload: dict) -> dict:
    """Call the resilient STAC client and map total failure to an honest 503."""

    if _stac is None:
        raise RuntimeError("stac_search.configure() must be called before stac_query()")
    try:
        return await _stac.search(payload)
    except RuntimeError as exc:
        if _logger is not None:
            _logger.error("STAC غير متاح (collections=%s): %s", payload.get("collections"), exc)
        raise HTTPException(
            503,
            "فهرس صور الأقمار (STAC) غير متاح حاليّاً من داخل الخدمة — "
            "تحقّق من اتّصال/DNS حاوية raster-service ثمّ أعد المحاولة",
        ) from exc


async def stac_search(
    bbox: list[float],
    dt_start: str,
    dt_end: str,
    max_cloud: float,
    limit: int,
    geometry: dict | None = None,
) -> dict:
    """Search historical Sentinel-2 scenes using CDSE by default."""

    import cdse_client as _cdse

    if HISTORICAL_SEARCH_PROVIDER == "element84":
        return await stac_search_element84(bbox, dt_start, dt_end, max_cloud, limit)
    if not _cdse.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "بحث الأقمار التاريخيّ يعتمد Copernicus/CDSE حصراً؛ الاعتمادات غائبة "
                "(CDSE_CLIENT_ID/SECRET أو SH_CLIENT_ID/SECRET). اضبطها، أو عيّن "
                "HISTORICAL_SEARCH_PROVIDER=element84 صراحةً لتجاوز واعٍ."
            ),
        )
    return await stac_search_cdse(bbox, dt_start, dt_end, max_cloud, limit, geometry)


async def stac_search_cdse(
    bbox: list[float],
    dt_start: str,
    dt_end: str,
    max_cloud: float,
    limit: int,
    geometry: dict | None = None,
) -> dict:
    """Discover Sentinel-2 scenes through the CDSE/Sentinel Hub catalogue."""

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
    except Exception as exc:  # noqa: BLE001 — catalog outage should degrade to empty list
        if _logger is not None:
            _logger.warning("CDSE catalog search failed: %s", exc)
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


async def stac_search_element84(
    bbox: list[float], dt_start: str, dt_end: str, max_cloud: float, limit: int
) -> dict:
    """Search Element84 Earth Search for Sentinel-2 scenes."""

    payload = {
        "collections": [SENTINEL_COLLECTION],
        "bbox": bbox,
        "datetime": f"{dt_start}/{dt_end}",
        "query": {"eo:cloud_cover": {"lte": max_cloud}},
        "limit": limit,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    data = await stac_query(payload)

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
                "bands_urls": band_urls_from_assets(assets),
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


async def stac_search_radar(bbox: list[float], dt_start: str, dt_end: str, limit: int) -> dict:
    """Search Element84 for Sentinel-1 GRD radar scenes."""

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


def landsat_thermal_href(assets: dict) -> str | None:
    """Select only the thermal/LST asset from Landsat C2 L2 STAC assets."""

    for key in LANDSAT_THERMAL_ASSET_CANDIDATES:
        href = (assets.get(key) or {}).get("href") if isinstance(assets.get(key), dict) else None
        if href:
            return href
    for key, asset in (assets or {}).items():
        lower_key = str(key).lower()
        title = str((asset or {}).get("title", "")).lower() if isinstance(asset, dict) else ""
        href = (asset or {}).get("href") if isinstance(asset, dict) else None
        if href and (
            "surface temperature" in title or "temperature" in lower_key or "thermal" in lower_key
        ):
            return href
    return None


def landsat_unique_payload(feat: dict) -> dict | None:
    props = feat.get("properties", {}) or {}
    assets = feat.get("assets", {}) or {}
    thermal_href = landsat_thermal_href(assets)
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


async def stac_search_landsat(
    bbox: list[float], dt_start: str, dt_end: str, max_cloud: float, limit: int
) -> dict:
    """Search Landsat C2 L2 as a thermal-unique layer only."""

    return await stac_search_landsat_unique(bbox, dt_start, dt_end, max_cloud, limit)


async def stac_search_landsat_unique(
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
    data = await stac_query(payload)
    items = []
    for feat in data.get("features", []):
        item = landsat_unique_payload(feat)
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


async def stac_search_dem(bbox: list[float]) -> dict:
    """Search Copernicus DEM tiles for an AOI."""

    payload = {
        "collections": [DEM_COLLECTION],
        "bbox": bbox,
        "limit": 20,
    }
    data = await stac_query(payload)
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
