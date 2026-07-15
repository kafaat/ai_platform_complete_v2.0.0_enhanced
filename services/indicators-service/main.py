#!/usr/bin/env python3
"""SAHOOL indicators-service — contract and aggregation boundary.

This service does not compute observed spectral indices. Raster-service owns
band math, scenes, COGs, quality masks, tiles, and observed time series.
Vegetation-analysis owns interpretation. The current service publishes the
canonical ownership contract and fails closed for spectral computation.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Query

_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))
from observation_runtime import fetch_canonical_observations  # noqa: E402
from observation_timeline import fetch_canonical_timeline  # noqa: E402

VERSION = os.getenv("SERVICE_VERSION", "9.1.0-contract-boundary")


def _resolve_manifest() -> Path:
    """Locate shared/contracts/indicator_ownership.json in both repo and container layouts.

    In the repo the file lives at <root>/shared/contracts/...; the container Dockerfile
    flattens it to /app/shared/contracts/... alongside main.py. Walking up from this file
    (parent first) finds it in either layout — a hardcoded parent-index into the repo tree
    raised IndexError at /app/main.py and took the whole service down on startup.
    """
    here = Path(__file__).resolve()
    for base in (here.parent, *here.parents):
        candidate = base / "shared" / "contracts" / "indicator_ownership.json"
        if candidate.exists():
            return candidate
    return here.parent / "shared" / "contracts" / "indicator_ownership.json"


_MANIFEST = _resolve_manifest()

app = FastAPI(title="SAHOOL Indicators Contract Service", version=VERSION)


def _manifest() -> dict:
    try:
        data = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=503, detail=f"indicator ownership manifest unavailable: {exc}"
        ) from exc
    if not data.get("products") or not data.get("policy"):
        raise HTTPException(status_code=503, detail="indicator ownership manifest is incomplete")
    return data


@app.get("/healthz")
async def healthz():
    return {"status": "alive", "service": "indicators-service", "version": VERSION}


@app.get("/health", include_in_schema=False)
async def legacy_health():
    return await healthz()


@app.get("/readyz")
async def ready():
    manifest = _manifest()
    return {
        "status": "ready",
        "service": "indicators-service",
        "implemented_runtime": True,
        "runtime_role": "canonical-observation-adapter",
        "spectral_compute": False,
        "observed_spectral_owner": manifest["policy"]["observed_spectral_owner"],
        "schema_version": manifest["schema_version"],
    }


@app.get("/v1/indicators/ownership")
async def ownership():
    return _manifest()


@app.get("/v1/indicators/catalog")
async def catalog():
    manifest = _manifest()
    return {
        "schema_version": manifest["schema_version"],
        "indicators": manifest["products"],
        "source": "canonical-indicator-ownership-manifest",
    }


@app.get("/capabilities")
async def capabilities():
    return {
        "schema_version": _manifest()["schema_version"],
        "service": "indicators-service",
        "implemented_runtime": True,
        "runtime_role": "canonical-observation-adapter",
        "capabilities": {
            "ownership_contract": True,
            "indicator_catalog": True,
            "indicator_compute": False,
            "tile_generation": False,
            "timeseries": True,
            "canonical_observation_adapter": True,
        },
        "owners": {
            "observed_spectral": "raster-service",
            "interpretation": "vegetation-analysis-service",
            "aggregation": "sahool-platform",
        },
    }


@app.get("/contract")
async def contract():
    return {
        "service": "indicators-service",
        "contract_version": "2026-07-12.riv-p0",
        "implemented_runtime": True,
        "runtime_role": "canonical-observation-adapter",
        "truth_policy": "single-owner-fail-closed",
        "allowed_routes": [
            "/healthz",
            "/readyz",
            "/capabilities",
            "/contract",
            "/v1/indicators/ownership",
            "/v1/indicators/catalog",
            "/v1/fields/{field_id}/observations",
            "/v1/fields/{field_id}/observation-timeline",
            "/",
        ],
    }


@app.post("/v1/indicators/compute")
async def compute_indicator():
    raise HTTPException(
        status_code=409,
        detail="observed spectral computation is exclusively owned by raster-service",
    )


@app.get("/")
async def root():
    return {
        "service": "indicators-service",
        "implemented_runtime": True,
        "runtime_role": "canonical-observation-adapter",
        "spectral_compute": False,
    }


@app.get("/v1/fields/{field_id}/observations")
async def field_observations(
    field_id: str,
    season_id: str = Query(..., min_length=1),
    indicators: str = Query("ndvi"),
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
):
    try:
        tenant_id = UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(400, "invalid X-Tenant-Id") from exc
    requested = [v.strip().lower() for v in indicators.split(",") if v.strip()]
    try:
        observations = await fetch_canonical_observations(
            field_id=field_id, tenant_id=tenant_id, season_id=season_id, indicators=requested
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(424, "canonical raster observation unavailable") from exc
    if not observations:
        raise HTTPException(424, "no consistent real canonical observation available")
    return {
        "field_id": field_id,
        "season_id": season_id,
        "source": "indicators-service",
        "canonical": True,
        "observations": [item.model_dump(mode="json") for item in observations],
    }


@app.get("/v1/fields/{field_id}/observation-timeline")
async def observation_timeline(
    field_id: str,
    season_id: str = Query(..., min_length=1),
    indicators: str = Query("ndvi"),
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
):
    try:
        tenant_id = UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(400, "invalid X-Tenant-Id") from exc
    requested = [v.strip().lower() for v in indicators.split(",") if v.strip()]
    try:
        entries = await fetch_canonical_timeline(
            field_id=field_id, tenant_id=tenant_id, season_id=season_id, indicators=requested
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(424, "canonical raster timeline unavailable") from exc
    if not entries:
        raise HTTPException(424, "no real canonical timeline available")
    latest = {}
    for item in entries:
        code = item.indicator.code
        if code not in latest and item.publication_status.value == "published":
            latest[code] = item.observation_ref
    return {
        "field_id": field_id,
        "season_id": season_id,
        "entries": [item.model_dump(mode="json") for item in entries],
        "latest_observation_refs": latest,
        "source": "indicators-service",
        "canonical": True,
        "supersession_projected": True,
    }
