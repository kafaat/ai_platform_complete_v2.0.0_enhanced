"""Runtime settings/constants for raster-service.

Extracted from main.py so the application module stays a thin façade while keeping
legacy ``main.CONSTANT`` compatibility through re-exports.
"""

from __future__ import annotations

import os

from shared.security.cors_policy import parse_cors_origins

EARTH_SEARCH_URL = os.getenv("EARTH_SEARCH_URL", "https://earth-search.aws.element84.com/v1")
# الافتراض element84: صور Sentinel-2 خام مباشرة (VRT محليّ) بلا وحدات معالجة CDSE.
# عيّن HISTORICAL_SEARCH_PROVIDER=cdse لاستعمال Copernicus Process API عند توفّر الرصيد.
HISTORICAL_SEARCH_PROVIDER = os.getenv("HISTORICAL_SEARCH_PROVIDER", "element84").strip().lower()
SENTINEL_COLLECTION = "sentinel-2-l2a"
SENTINEL1_COLLECTION = "sentinel-1-grd"
LANDSAT_COLLECTION = "landsat-c2-l2"
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
DEM_COLLECTION = "cop-dem-glo-30"
CORS_ORIGINS = parse_cors_origins(os.getenv("CORS_ORIGINS"), allow_credentials=True)
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30"))
TITILER_URL = os.getenv("TITILER_URL", "")
PC_STAC_URL = os.getenv(
    "PLANETARY_COMPUTER_URL", "https://planetarycomputer.microsoft.com/api/stac/v1"
)
DEAFRICA_STAC_URL = os.getenv("DEAFRICA_STAC_URL", "https://explorer.digitalearth.africa/stac")
CLOUD_PCT_WARN_THRESHOLD = float(os.getenv("CLOUD_PCT_WARN_THRESHOLD", "20"))
UPLOAD_DIR = os.getenv("RASTER_UPLOAD_DIR", "/tmp/sahool_rasters")
OFFLINE_PACKS_DIR = os.path.join(UPLOAD_DIR, "offline_packs")
SSRF_BLOCKED_HOSTS = {"169.254.169.254", "metadata.google.internal", "metadata"}
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")
LAYER_EVICT_CHANNEL = "sahool:raster:layer-evict"


def stac_fallback_chain() -> list[str]:
    """Return the configured STAC fallback chain, preserving main.py behavior."""
    fallback_chain: list[str] = []
    if os.getenv("STAC_FALLBACK_ENABLED", "true") == "true":
        fallback_chain.append(PC_STAC_URL)
    if os.getenv("DEAFRICA_ENABLED", "false") == "true":
        fallback_chain.append(DEAFRICA_STAC_URL)
    return fallback_chain


# Fully transparent 1×1 PNG used whenever real raster data is unavailable.
TRANSPARENT_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f"
    "15c4890000000d49444154789c6360606060000000050001a5f64540000000"
    "0049454e44ae426082"
)

# Finite nodata used in generated COGs. NaN nodata can produce unstable GDAL masks/overviews.
RASTER_NODATA = -9999.0


# ── سقف قراءة الراستر (UNBOUNDED-RASTER-READ-ON-ARBITRARY-URL-01) ──────────────
#
# مقيس 2026-08-06: ``process_precomputed_truecolor`` و``apply_polygon_mask_uint8``
# يستدعيان ``src.read()`` بلا أيّ حدّ، و``safe_raster_source`` يقبل **أيّ** رابط
# ``http(s)`` غير محجوب. فنداءٌ إلى ``/process`` بـ``indicator=truecolor`` ورابطٍ كبير
# يُخصّص المصفوفة كاملةً قبل أن يعرف أحدٌ حجمها.
#
# **وتصنيف تقرير الشهادة كان صحيحاً في نوعه وخاطئاً في سببه:** نُسِب العطل إلى «قراءة
# مشهد Sentinel-2 كامل» عبر مسار CDSE — والقياس يُكذّب ذلك: ``process_backfill_scene_cdse``
# يستدعي ``process_index(bbox=…, geometry=clip)``، فالراستر **مقصوصٌ على حدود الحقل قبل
# أن يصل الخدمة**. المسار الإنتاجيّ محدود؛ غير المحدود هو الرابط الحرّ.
#
# السقف الافتراضيّ ٦٤ م.بكسل‑نطاق: مشهد S2 كامل RGBA = ١٢١ م.بكسل × ٤ نطاقات = ٤٨٢
# م.بكسل‑نطاق (٤٨٢ م.بايت uint8) مقابل ``mem_limit`` قدره 1536m للخدمة — والذروة تتجاوز
# ذلك لأنّ القناع والكتابة يخصّصان أيضاً. وحقلٌ حقليّ نموذجيّ أصغر من ذلك بمراتب.
# يُرفَع بمتغيّر بيئة عند الحاجة؛ **الرفض المُعلَن أصدق من OOM صامت**.
RASTER_MAX_READ_BAND_PIXELS = int(os.getenv("RASTER_MAX_READ_BAND_PIXELS", str(64_000_000)))
