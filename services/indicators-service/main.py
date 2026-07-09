#!/usr/bin/env python3
"""SAHOOL indicators-service — health-only runtime boundary.

This container is intentionally health-only in the current architecture. Real
indicator computation is still owned by sahool-platform/raster paths. The service
must not report production readiness for computation until that ownership is
moved here. It therefore exposes /healthz for process liveness and /readyz as
``degraded`` rather than pretending that indicator computation is implemented.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

VERSION = os.getenv("SERVICE_VERSION", "9.0.0-health-only")

app = FastAPI(
    title="SAHOOL Indicators Service (health-only)",
    version=VERSION,
    description="Health-only boundary; real indicator computation is not owned by this service yet.",
)


@app.get("/healthz")
async def healthz():
    return {"status": "alive", "service": "indicators-service", "version": VERSION}


@app.get("/health", include_in_schema=False)
async def legacy_health():
    return await healthz()


@app.get("/readyz")
async def ready(response=None):
    # Honest readiness: process is alive, but indicator computation is not implemented here.
    return {
        "status": "degraded",
        "service": "indicators-service",
        "implemented_runtime": False,
        "health_only": True,
        "owner": "sahool-platform/raster-service",
        "reason": "indicator computation is not yet owned by indicators-service",
    }


@app.get("/capabilities")
async def capabilities():
    return {
        "service": "indicators-service",
        "schema_version": "2026-07-09.capabilities",
        "implemented_runtime": False,
        "health_only": True,
        "capabilities": {
            "process_liveness": True,
            "indicator_compute": False,
            "tile_generation": False,
            "timeseries": False,
        },
        "handoff_owner": "sahool-platform/raster-service",
    }


@app.get("/contract")
async def contract():
    return {
        "service": "indicators-service",
        "contract_version": "2026-07-09.health-only",
        "implemented_runtime": False,
        "truth_policy": "fail-closed-for-computation",
        "allowed_routes": ["/healthz", "/readyz", "/capabilities", "/contract", "/"],
        "handoff_owner": "sahool-platform/raster-service",
    }


@app.post("/v1/indicators/compute")
async def compute_indicator():
    raise HTTPException(
        status_code=501,
        detail=(
            "indicators-service is health-only in this build; computation is still owned "
            "by sahool-platform/raster-service. No fabricated indicator result is returned."
        ),
    )


@app.get("/")
async def root():
    return {
        "service": "indicators-service",
        "implemented_runtime": False,
        "health_only": True,
        "note": "Indicator computation is not implemented in this service; no fabricated results are returned.",
    }
