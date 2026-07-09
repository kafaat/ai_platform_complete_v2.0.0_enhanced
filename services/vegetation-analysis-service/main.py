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

import asyncio
import hashlib
import json
import logging
import math
import os
import re
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta

import httpx
import jwt as _jwt
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from prometheus_client import (
    CONTENT_TYPE_LATEST,  # noqa: F401 — يُستخدَم عبر main.X في routers/health.py
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,  # noqa: F401 — يُستخدَم عبر main.X في routers/health.py
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
from vegetation_runtime import (  # noqa: E402,F401
    NATS_URL, CORS_ORIGINS, RASTER_SERVICE_URL, VEGETATION_PREFER_RASTER,
    _RASTER_REAL_INDEX, SH_CLIENT_ID, SH_CLIENT_SECRET, SH_TOKEN_URL, SH_PROCESS_URL,
    CDSE_USER, CDSE_PASSWORD, FEATURE_SENTINEL_DB_FIELDS, ALLOW_LEGACY_FIELD_REGISTRY,
    PLATFORM_API_URL, security, _verify_claims, _tenant_from_claims, _valid_date,
    ANALYSIS_COUNT, ANALYSIS_LATENCY, FIELD_REGISTRY, select_field_source,
    load_field, fetch_from_sentinel_hub, fetch_from_cdse, run_analysis,
    _generate_timeseries, _current_ndvi_payload, CONTENT_TYPE_LATEST, generate_latest,
)
import vegetation_runtime as _vegetation_runtime  # noqa: E402
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
