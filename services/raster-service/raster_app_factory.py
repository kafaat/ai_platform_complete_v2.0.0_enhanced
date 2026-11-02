"""FastAPI application factory for raster-service.

This module owns app construction, CORS wiring, tenant-context middleware, and
router registration so ``main.py`` remains a thin bootstrap/compatibility
facade.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import raster_security_context
from fastapi import FastAPI, HTTPException
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

    @app.middleware("http")
    async def tenant_context_middleware(request, call_next):
        # tid مخالف للمستأجر الموثَّق ⇒ 403 صريح لا 500 (الوسيط خارج معالجات FastAPI).
        try:
            tenant = raster_security_context.tenant_from_request(request)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        token = raster_security_context.REQ_TENANT.set(tenant)
        try:
            return await call_next(request)
        finally:
            raster_security_context.REQ_TENANT.reset(token)

    # CORS يُضاف **بعد** وسيط المستأجر عمداً: في Starlette آخِرُ وسيطٍ يُضاف هو الأبعد فيعمل
    # أوّلاً. كان CORS داخليّاً فرُفِض طلب المتصفّح التمهيديّ (OPTIONS بلا Authorization/
    # X-Tenant-Id) 403 من فحص ``tid`` فلا يُرسَل الطلب الحقيقيّ (مراجعة #1330). الآن يجيب CORS
    # التمهيديَّ بنفسه دون بلوغ أيّ معالج، والطلب الحقيقيّ يمرّ بفحص المستأجر كما كان — وردُّ
    # رفضه يحمل ترويسات CORS فيقرؤه المتصفّح. (test_cors_preflight_tenant_order.py)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Tenant-Id"],
        allow_credentials=True,
    )
    register_routers(app)
    return app
