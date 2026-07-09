"""
SAHOOL v9.1 — vegetation-analysis-service/main.py (FULLY FIXED)
══════════════════════════════════════════════════════════════
إصلاحات:
  ✅ أكمل الملف المقطوع (lifespan + app + endpoints)
  ✅ أزل field_id من Prometheus labels (cardinality explosion)
  ✅ استبدل datetime.now(timezone.utc) بـ datetime.now(timezone.utc)
  ✅ أضف auth dependency على endpoints الحساسة

NOTE ON DATA PROVENANCE (honesty):
  This service does NOT decode satellite raster pixels. It deliberately
  avoids heavy geospatial dependencies (rasterio/GDAL). It may make REAL
  authenticated calls to Sentinel Hub / CDSE to confirm provider reachability
  and acquisition metadata, but the returned GeoTIFF bytes are NOT decoded
  here. The vegetation indices returned by this service are therefore
  FIELD-MEAN ESTIMATES computed from deterministic synthetic bands (seeded by
  field + date), NOT from real per-pixel reflectance.

  Real per-pixel raster processing (decoding the GeoTIFF, masking via SCL,
  averaging real reflectance) lives in the raster-service, which ships rasterio.

  EXCEPTION — real per-pixel pass-through (VEGETATION_PREFER_RASTER, ON by default):
  /v1/analyze prefers the REAL per-pixel mean from raster-service (band_math over
  free public Sentinel-2 via STAC, no credentials) when the field has a processed
  layer — for NDVI, EVI, SAVI (MSAVI2) and NDMI (moisture). It substitutes those
  values only and marks each per-index `source` as "raster-service"; the rest
  (lai/cwsi/ndwi/gndvi/recl) stay "estimate" — lai needs a model, cwsi a thermal
  band (LST), the others bands/formulas outside band_math. `data_source`/`real_data`
  remain NDVI-centric (the health card is built on NDVI). Any failure/timeout/
  missing layer falls back per-index to the labeled estimate (behaviour never degrades).
  `provider_reachable` indicates whether the live SH/CDSE metadata API responded.
"""

from __future__ import annotations

import asyncio  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
import hashlib  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
import json  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
import logging
import math  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
import os  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
import re  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
from contextlib import asynccontextmanager
from datetime import (  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    UTC,
    date,
    datetime,
    timedelta,
)

import httpx  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
import jwt as _jwt  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
from fastapi import FastAPI, HTTPException  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
from prometheus_client import (
    CollectorRegistry,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    Counter,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    Histogram,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
)

try:
    from shared.logging_config import setup_logging

    logger = setup_logging("vegetation-analysis-service")
except ImportError:
    logging.basicConfig(
        level=logging.INFO, format='{"time":"%(asctime)s","svc":"vegetation","msg":"%(message)s"}'
    )
    logger = logging.getLogger("vegetation-analysis-service")

# ── Vegetation runtime (P1 decomposition) ───────────────────────
import vegetation_runtime as _vegetation_runtime  # noqa: E402
from vegetation_runtime import (  # noqa: E402,F401
    _RASTER_REAL_INDEX,
    ALLOW_LEGACY_FIELD_REGISTRY,
    ANALYSIS_COUNT,
    ANALYSIS_LATENCY,
    CDSE_PASSWORD,
    CDSE_USER,
    CONTENT_TYPE_LATEST,
    CORS_ORIGINS,
    FEATURE_SENTINEL_DB_FIELDS,
    FIELD_REGISTRY,
    NATS_URL,
    PLATFORM_API_URL,
    RASTER_SERVICE_URL,
    SH_CLIENT_ID,
    SH_CLIENT_SECRET,
    SH_PROCESS_URL,
    SH_TOKEN_URL,
    VEGETATION_PREFER_RASTER,
    _current_ndvi_payload,
    _generate_timeseries,
    _tenant_from_claims,
    _valid_date,
    _verify_claims,
    fetch_from_cdse,
    fetch_from_sentinel_hub,
    generate_latest,
    load_field,
    run_analysis,
    security,
    select_field_source,
)


# ── Lifespan ───────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    sh_configured = bool(SH_CLIENT_ID and SH_CLIENT_SECRET)
    cdse_configured = bool(CDSE_USER and CDSE_PASSWORD)
    logger.info(
        f"✅ vegetation-service v9.1 starting — SH={'✅' if sh_configured else '❌ fallback'} | CDSE={'✅' if cdse_configured else '❌ fallback'}"
    )
    yield
    if _vegetation_runtime._nc:
        await _vegetation_runtime._nc.close()
        _vegetation_runtime._nc = None
        logger.info("NATS connection closed")


app = FastAPI(title="SAHOOL Vegetation Analysis", version="9.1.0", lifespan=lifespan)
# ✅ OTEL
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    logger.debug("OTEL غير مثبّت — التتبّع معطّل (اختياري)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)


from router_registry import register_routers  # noqa: E402

register_routers(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
