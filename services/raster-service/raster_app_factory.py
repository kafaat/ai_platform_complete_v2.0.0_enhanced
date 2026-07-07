"""FastAPI application factory for raster-service.

This module owns app construction, CORS wiring, tenant-context middleware, and
router registration so ``main.py`` remains a thin bootstrap/compatibility
facade.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import raster_security_context
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from router_registry import register_routers


def create_raster_app(
    *,
    title: str,
    version: str,
    lifespan: Any,
    cors_origins: Iterable[str],
) -> FastAPI:
    """Build and fully wire the raster-service FastAPI app."""
    app = FastAPI(title=title, version=version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Tenant-Id"],
        allow_credentials=True,
    )

    @app.middleware("http")
    async def tenant_context_middleware(request, call_next):
        token = raster_security_context.REQ_TENANT.set(
            raster_security_context.tenant_from_request(request)
        )
        try:
            return await call_next(request)
        finally:
            raster_security_context.REQ_TENANT.reset(token)

    register_routers(app)
    return app
