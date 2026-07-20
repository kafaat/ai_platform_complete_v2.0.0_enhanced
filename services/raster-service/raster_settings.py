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
