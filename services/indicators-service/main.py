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
from pathlib import Path

from fastapi import FastAPI, HTTPException

VERSION = os.getenv("SERVICE_VERSION", "9.1.0-contract-boundary")
_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "shared" / "contracts" / "indicator_ownership.json"

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
        "runtime_role": "contract-only",
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
        "runtime_role": "contract-only",
        "capabilities": {
            "ownership_contract": True,
            "indicator_catalog": True,
            "indicator_compute": False,
            "tile_generation": False,
            "timeseries": False,
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
        "runtime_role": "contract-only",
        "truth_policy": "single-owner-fail-closed",
        "allowed_routes": [
            "/healthz",
            "/readyz",
            "/capabilities",
            "/contract",
            "/v1/indicators/ownership",
            "/v1/indicators/catalog",
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
        "runtime_role": "contract-only",
        "spectral_compute": False,
    }
