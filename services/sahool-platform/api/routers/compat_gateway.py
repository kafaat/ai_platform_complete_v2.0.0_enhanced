"""api/routers/compat_gateway.py — توافقيّة بوّابة قديمة (legacy aliases/passthrough)
=================================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter``.

نقاط توافقيّة (``/api/...`` لا ``/api/v1/...``) تبقى خارج النطاق الأساسيّ للمنصّة:
أسماء بديلة لفحوص الصحّة (health aliases) + تمرير (passthrough) ضيّق إلى خدمات
``vegetation``/``raster`` حين تُمرّر بيئات nginx/compose قديمة مساراتها إلى المنصّة.

نُقلت الدوالّ من ``main.py`` مع تغيير ``@app`` إلى ``@router``. يستورد تبعيّة المصادقة
``get_current_user`` من ``api.main`` كبقيّة الراوترات (يُحمَّل بعد تعريفها، فلا دورة).
"""

from __future__ import annotations

import os
import re

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from api.main import UserSchema, get_current_user
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
# 404 في سجلات المنصّة عند طلب TileJSON/tiles. هذا fallback ضيق لمسارات GET
# فقط حتى لا تنكسر خرائط الحقول عند اختلاف ترتيب locations. التوجيه الصحيح يبقى
# nginx /api/raster/ → raster-service مباشرة.
# P2.4: even this legacy path uses api.raster_service_client for raster transport.
#
# T4 (تدقيق 2026-11-01): كان التمرير بلا مصادقة ويُرفق رمز الخدمة بأيّ مسار/مستأجر يختاره
# المتّصل ⇒ وصول مجهول لمسارات raster الخدميّة (حزم offline، إحصاءات التخزين، المهامّ).
# الآن يطابق عقد بوّابة nginx: JWT إلزاميّ، المستأجر من التوكن لا من الطلب، بلا رمز خدمة،
# وقائمة مسموحات صريحة لمسارات قراءة المتصفّح/الجوّال (مطابقة كاملة لمقاطع ضيّقة الأحرف،
# فلا substring ولا ``..`` ولا ترميز ``%``).
_ID = r"[A-Za-z0-9_-]{1,128}"
_XYZ = r"[0-9]{1,2}/[0-9]{1,10}/[0-9]{1,10}"
_RASTER_COMPAT_GET_ALLOWLIST: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        rf"v1/fields/{_ID}/tilejson",
        rf"v1/fields/{_ID}/tiles/{_XYZ}\.png",
        rf"v1/fields/{_ID}/cdse-tilejson",
        rf"v1/fields/{_ID}/cdse-tiles/{_XYZ}\.png",
        rf"v1/fields/{_ID}/cdse-thumbnail\.png",
        rf"v1/fields/{_ID}/indicator-grid",
        rf"v1/fields/{_ID}/timeseries",
        rf"v1/fields/{_ID}/contours\.geojson",
        rf"v1/fields/{_ID}/soil/sampling-plan",
        rf"v1/elevation/hillshade/{_XYZ}\.png",
        rf"v1/slope/{_XYZ}\.png",
        r"v1/terrain/tilejson",
        r"v1/soil/tilejson",
        rf"v1/soil/tiles/{_ID}/{_ID}/{_XYZ}\.png",
        r"v1/soil/properties",
        r"v1/imagery/backfill/policy",
    )
)
# مُعامِلات لا تُمرَّر: المستأجر يأتي من التوكن، والتوكن لا يُسرَّب في رابط الخدمة.
_RASTER_COMPAT_DROPPED_PARAMS = frozenset({"tid", "tenant_id", "access_token"})


def _raster_compat_path_allowed(path: str) -> bool:
    """مطابقة كاملة لمسار مُطبَّع ضدّ القائمة؛ أيّ ``..``/``%``/``\\``/مقطع فارغ ⇒ مرفوض."""
    if not path or "%" in path or "\\" in path:
        return False
    if any(seg in ("", ".", "..") for seg in path.split("/")):
        return False
    return any(p.fullmatch(path) for p in _RASTER_COMPAT_GET_ALLOWLIST)


@router.get("/api/raster/{path:path}")
async def raster_api_passthrough(
    path: str,
    request: Request,
    user: UserSchema = Depends(get_current_user),
    authorization: str | None = Header(None),
):
    """Authenticated compatibility passthrough for misrouted raster GET requests.

    Mirrors the nginx ``/api/raster/`` gateway contract: a valid JWT is required,
    the tenant comes from the token (client ``X-Tenant-Id``/``tid`` are ignored),
    the raster service token is never attached, and only an explicit allowlist of
    browser/mobile read paths is forwarded (anything else ⇒ 404).
    """
    # ``path`` يصل مفكوك الترميز؛ أيّ ``%`` في المسار الخام (``%2f``/``%2e``) يُرفَض أيضاً.
    raw_path = request.scope.get("raw_path") or b""
    if b"%" in raw_path or not _raster_compat_path_allowed(path):
        raise HTTPException(status_code=404, detail="raster compat path not allowed")
    params = {
        k: v for k, v in request.query_params.items() if k not in _RASTER_COMPAT_DROPPED_PARAMS
    }
    content, status_code, media_type, forwarded_headers = await raster_get_raw(
        path,
        tenant_id=str(user.tenant_id),
        authorization=authorization,
        params=params,
        timeout_s=30.0,
    )
    return Response(
        content=content,
        status_code=status_code,
        media_type=media_type,
        headers=forwarded_headers,
    )
