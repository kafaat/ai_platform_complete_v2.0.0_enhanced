"""api/routers/compat_gateway.py — توافقيّة بوّابة قديمة (legacy aliases/passthrough)
=================================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter``.

نقاط توافقيّة (``/api/...`` لا ``/api/v1/...``) تبقى خارج النطاق الأساسيّ للمنصّة:
أسماء بديلة لفحوص الصحّة (health aliases) + تمرير (passthrough) ضيّق إلى خدمات
``vegetation``/``raster`` حين تُمرّر بيئات nginx/compose قديمة مساراتها إلى المنصّة.

سلوك محفوظ بالكامل: نُقلت الدوالّ حرفيّاً من ``main.py`` مع تغيير ``@app`` إلى
``@router`` — لا تستورد من ``api.main`` (لا دورة استيراد) فتُضمَّن آليّاً.
"""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, Response

from api.raster_service_client import raster_get_raw

router = APIRouter()


# ─── P3 Compatibility aliases for legacy frontend/service health routes ───
def _health_alias_response(service: str, target: str | None = None, mode: str = "alias"):
    return {"status": "ready", "service": service, "mode": mode, "target": target}


@router.get("/api/indicators/readyz")
async def indicators_readyz_alias():
    # indicators-service is a health stub; real dashboard remains under /api/v1/indicators.
    return _health_alias_response("indicators-service", "/api/v1/indicators/dashboard")


@router.get("/api/weather/readyz")
async def weather_readyz_alias():
    # weather runtime currently lives in sahool-platform; keep legacy probe green.
    return _health_alias_response("weather-service", "/api/v1/weather/current")


@router.get("/api/vegetation/readyz")
async def vegetation_readyz_alias():
    return _health_alias_response("vegetation-analysis-service", "/api/vegetation/v1/analyze")


@router.get("/api/agent/health")
async def agent_health_alias():
    return _health_alias_response("supervisor-agent", "/health")


@router.get("/api/vegetation/v1/all_fields")
async def vegetation_all_fields_passthrough(
    request: Request,
    authorization: str | None = Header(None),
    x_tenant_id: str | None = Header(None),
):
    # Compatibility fallback if nginx routes /api/vegetation/* to sahool-platform.
    vegetation_url = os.getenv(
        "VEGETATION_SERVICE_URL", "http://sahool-vegetation-analysis:8000"
    ).rstrip("/")
    query = str(request.url.query or "")
    target = f"{vegetation_url}/v1/all_fields" + (f"?{query}" if query else "")
    headers: dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    if x_tenant_id:
        headers["X-Tenant-Id"] = x_tenant_id
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(target, headers=headers)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"vegetation-service غير متاح: {e}") from e
    return Response(
        content=r.content, status_code=r.status_code, media_type=r.headers.get("content-type")
    )


@router.get("/api/vegetation/v1/analyze")
async def vegetation_analyze_passthrough(
    request: Request,
    authorization: str | None = Header(None),
    x_tenant_id: str | None = Header(None),
):
    vegetation_url = os.getenv(
        "VEGETATION_SERVICE_URL", "http://sahool-vegetation-analysis:8000"
    ).rstrip("/")
    query = str(request.url.query or "")
    target = f"{vegetation_url}/v1/analyze" + (f"?{query}" if query else "")
    headers: dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    if x_tenant_id:
        headers["X-Tenant-Id"] = x_tenant_id
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(target, headers=headers)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"vegetation-service غير متاح: {e}") from e
    return Response(
        content=r.content, status_code=r.status_code, media_type=r.headers.get("content-type")
    )


# ─── Compatibility proxy: raster paths accidentally routed to sahool-platform ───
# بعض بيئات nginx/compose القديمة تمرّر /api/raster/* إلى sahool-platform، فيظهر
# 404 في سجلات المنصّة عند طلب TileJSON/tiles. هذا fallback ضيق وآمن لمسارات GET
# فقط حتى لا تنكسر خرائط الحقول عند اختلاف ترتيب locations. التوجيه الصحيح يبقى
# nginx /api/raster/ → raster-service مباشرة.
# P2.4: even this legacy path uses api.raster_service_client for raster transport.


@router.get("/api/raster/{path:path}")
async def raster_api_passthrough(
    path: str,
    request: Request,
    x_tenant_id: str | None = Header(None),
    authorization: str | None = Header(None),
):
    """Compatibility passthrough for misrouted raster GET requests.

    Browsers load map tiles as <img>, so custom headers may be absent. Preserve
    the original query string and promote ?tid=... to X-Tenant-Id for the
    raster-service. Without this, /api/raster/.../tilejson?index=...&tid=...
    can still return 404/403 when the request lands on sahool-platform instead
    of nginx's raster upstream.
    """
    tenant_from_query = request.query_params.get("tid") or request.query_params.get("tenant_id")
    content, status_code, media_type, forwarded_headers = await raster_get_raw(
        path,
        tenant_id=x_tenant_id or tenant_from_query,
        authorization=authorization,
        params=dict(request.query_params),
        timeout_s=30.0,
    )
    return Response(
        content=content,
        status_code=status_code,
        media_type=media_type,
        headers=forwarded_headers,
    )
