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
from fastapi.responses import JSONResponse
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
        # القرار هنا لا في كلّ راوتر: كلُّ ما يقرأ REQ_TENANT يرث القاعدة نفسها، فلا نقطةَ
        # جديدةٌ تستطيع أن تنساها (raster_security_context: مَن يحقّ له أن يُسمّي المستأجِر).
        decision = raster_security_context.tenant_assertion_for_request(request)
        raster_security_context.record_tenant_assertion(
            decision, method=request.method, path=request.url.path
        )
        if decision.status is not None:
            return JSONResponse(
                status_code=decision.status,
                content={"detail": decision.detail, "code": decision.outcome},
            )
        token = raster_security_context.REQ_TENANT.set(decision.tenant)
        try:
            return await call_next(request)
        finally:
            raster_security_context.REQ_TENANT.reset(token)

    register_routers(app)
    return app
