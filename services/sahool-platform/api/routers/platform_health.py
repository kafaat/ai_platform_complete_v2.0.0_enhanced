"""Platform health/readiness/metrics routes extracted from api.main.

Behavior-preserving P1 decomposition: routes keep the same paths and response
contracts, while main.py keeps only bootstrap/shared state.
"""

from __future__ import annotations

import logging

from core.api_adapter import db_probe_ok, handle_healthz, handle_readyz
from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

from api import main

router = APIRouter()


# Runtime identity is read from a build-time generated, read-only image file.
# Mutable runtime environment values are deliberately not trusted. Operational
# endpoint (build/image identity) — same infrastructure class as /healthz.
@router.get("/runtime-identity", include_in_schema=True)
def runtime_evidence_identity():
    from shared.runtime_identity import load_build_identity

    return load_build_identity("sahool-platform")


@router.get("/healthz")
def healthz():
    """Liveness — no dependency; only process availability."""
    resp = handle_healthz()
    return JSONResponse(status_code=resp.status_code, content=resp.body)


@router.get("/metrics")
def metrics():
    """Minimal Prometheus-compatible platform metrics endpoint."""
    db_enabled = 1 if main._DB_POOL is not None else 0
    payload = "\n".join(
        [
            "# HELP sahool_platform_up Platform process is serving requests",
            "# TYPE sahool_platform_up gauge",
            "sahool_platform_up 1",
            "# HELP sahool_platform_db_pool_enabled Database pool configured",
            "# TYPE sahool_platform_db_pool_enabled gauge",
            f"sahool_platform_db_pool_enabled {db_enabled}",
            "# HELP sahool_platform_rate_limit_buckets In-process rate limit bucket count",
            "# TYPE sahool_platform_rate_limit_buckets gauge",
            f"sahool_platform_rate_limit_buckets {len(main._rate_buckets)}",
            "",
        ]
    )
    return PlainTextResponse(payload, media_type="text/plain; version=0.0.4")


@router.get("/readyz")
async def readyz():
    """Readiness — checks core plus actual DB dependency."""
    resp = handle_readyz()
    if resp.status_code != 200:
        return JSONResponse(status_code=resp.status_code, content=resp.body)
    if not await db_probe_ok(main._DB_POOL):
        body = dict(resp.body)
        body.update({"status": "not ready", "db": "down"})
        logging.warning("readyz: فحص القاعدة فشل — not ready (503)")
        return JSONResponse(status_code=503, content=body)
    return JSONResponse(status_code=resp.status_code, content=resp.body)
