"""Legacy Sentinel-Hub compatibility facade.

Observed spectral computation is exclusively owned by raster-service.  This
module intentionally contains no evalscripts or band math.  It remains only to
preserve old import/HTTP surfaces while consumers migrate to the canonical
Raster and Vegetation APIs.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query

RASTER_SERVICE_URL = os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8000").rstrip(
    "/"
)
VEGETATION_SERVICE_URL = os.getenv(
    "VEGETATION_SERVICE_URL", "http://sahool-vegetation-analysis:8000"
).rstrip("/")
INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "")
LEGACY_DIRECT_SENTINEL_ENABLED = (
    False  # permanently disabled; raster-service is the production owner
)

app = FastAPI(title="Legacy Vegetation Compatibility Facade", version="10.0-raster-owned")

# Kept only for legacy UI labels. Coordinates are not used to fetch providers.
FIELDS: dict[str, dict[str, Any]] = {
    "field_01": {"name": "حقل وادي سبأ", "lat": 15.05, "lon": 45.55, "crop": "قمح صلب"},
    "field_02": {"name": "حقل البيضاء الشمالي", "lat": 15.02, "lon": 45.58, "crop": "شعير"},
}


def _headers(tenant_id: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if INTERNAL_SERVICE_TOKEN:
        headers["X-Agent-Token"] = INTERNAL_SERVICE_TOKEN
    if tenant_id:
        headers["X-Tenant-Id"] = tenant_id
    return headers


async def _fetch_sentinel_hub(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Removed direct-provider path retained as a fail-closed import shim."""
    raise RuntimeError(
        "direct Sentinel-Hub computation was removed; read validated observations from raster-service"
    )


async def _proxy_json(
    url: str, *, params: dict[str, Any] | None = None, tenant_id: str | None = None
) -> Any:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params, headers=_headers(tenant_id))
    except httpx.HTTPError as exc:
        raise HTTPException(503, "canonical observation service unavailable") from exc
    if response.status_code == 424:
        raise HTTPException(424, response.json())
    if response.status_code >= 400:
        raise HTTPException(response.status_code, "canonical observation request failed")
    return response.json()


@app.post("/v1/analyze")
@app.get("/v1/analyze/{field_id}")
async def analyze(
    field_id: str,
    tenant_id: str | None = Query(None),
    date_value: str = Query("latest", alias="date"),
):
    """Delegate vegetation interpretation to its canonical owner."""
    return await _proxy_json(
        f"{VEGETATION_SERVICE_URL}/v1/analyze/{field_id}",
        params={"date": date_value},
        tenant_id=tenant_id,
    )


@app.get("/v1/timeseries/{field_id}")
async def timeseries(
    field_id: str,
    index: str = Query("ndvi"),
    tenant_id: str | None = Query(None),
):
    return await _proxy_json(
        f"{RASTER_SERVICE_URL}/v1/fields/{field_id}/timeseries",
        params={"index": index},
        tenant_id=tenant_id,
    )


@app.get("/v1/pixel-value")
async def pixel_value(
    field_id: str,
    lat: float,
    lon: float,
    index: str = Query("ndvi"),
    tenant_id: str | None = Query(None),
):
    return await _proxy_json(
        f"{RASTER_SERVICE_URL}/v1/fields/{field_id}/pixel",
        params={"lat": lat, "lon": lon, "index": index},
        tenant_id=tenant_id,
    )


@app.get("/v1/overview")
async def overview():
    return {
        "service": "legacy-vegetation-facade",
        "runtime_role": "compatibility-only",
        "observed_spectral_owner": "raster-service",
        "interpretation_owner": "vegetation-analysis-service",
        "direct_provider_fetch": False,
        "fields": FIELDS,
    }


@app.get("/healthz")
@app.get("/health")
async def health():
    return {"status": "alive", "service": "legacy-vegetation-facade"}


@app.get("/readyz")
async def readyz():
    return {
        "status": "ready",
        "runtime_role": "compatibility-only",
        "direct_provider_fetch": False,
    }
