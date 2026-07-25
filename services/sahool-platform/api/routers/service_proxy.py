"""api/routers/service_proxy.py — بوابات آمنة للخدمات الداخلية التي تحتاج X-Agent-Token.

الغرض: تفعيل وظائف الواجهة دون كشف SAHOOL_AGENT_TOKEN للمتصفح/Flutter.
المستخدم يقدّم JWT عادي؛ sahool-platform يتحقق من المستخدم ثم يحقن توكن الخدمة
و X-Tenant-Id قبل تمرير الطلب إلى edge/soil.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from api.main import UserSchema, get_current_user

router = APIRouter()

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _service_token() -> str:
    token = os.getenv("SAHOOL_AGENT_TOKEN", "").strip()
    if not token:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — proxy الخدمات الداخلية معطّل بأمان")
    return token


def _field_forms_token() -> str:
    # توكن قناة field-forms مخصّص (لا SAHOOL_AGENT_TOKEN المشترك — عزل القنوات، نمط SCOUT_INGEST_READ_TOKEN).
    token = os.getenv("FIELD_FORMS_SERVICE_TOKEN", "").strip()
    if not token:
        raise HTTPException(
            503, "FIELD_FORMS_SERVICE_TOKEN غير مضبوط — proxy النماذج الميدانيّة معطّل بأمان"
        )
    return token


def _filtered_headers(
    request: Request,
    user: UserSchema,
    *,
    service_header: tuple[str, str] | None = None,
    inject_actor: bool = False,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lk = key.lower()
        if lk in _HOP_BY_HOP:
            continue
        # لا نثق بأي ترويسات خدمة/مستأجر قادمة من العميل.
        if lk in {"x-agent-token", "x-tenant-id", "x-field-forms-token"}:
            continue
        # field-forms: هويّة الفاعل تُحقَن من JWT — ادّعاء العميل مرفوض.
        if inject_actor and lk == "x-actor-id":
            continue
        # Slice 3: لا تُمرَّر مصادقة العميل (JWT/جلسة) للخدمات الداخليّة — المصادقة
        # الداخليّة عبر توكن القناة المحقون + X-Tenant-Id حصرًا (منع تمرير هويّة العميل).
        if lk in {"authorization", "cookie"}:
            continue
        headers[key] = value
    if service_header is not None:
        headers[service_header[0]] = service_header[1]
    else:
        headers["X-Agent-Token"] = _service_token()
    headers["X-Tenant-Id"] = str(user.tenant_id)
    if inject_actor:
        headers["X-Actor-Id"] = str(user.user_id)
    return headers


def _response_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers:
        if key.lower() in _HOP_BY_HOP:
            continue
        out[key] = value
    return out


async def _proxy(
    *,
    request: Request,
    user: UserSchema,
    base_url: str,
    path: str,
    timeout: float = 120.0,
    service_header: tuple[str, str] | None = None,
    inject_actor: bool = False,
) -> Response:
    if request.method.upper() not in _ALLOWED_METHODS:
        raise HTTPException(405, "method not allowed")
    target = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream = await client.request(
                request.method,
                target,
                params=request.query_params,
                headers=_filtered_headers(
                    request, user, service_header=service_header, inject_actor=inject_actor
                ),
                content=body,
            )
    except httpx.TimeoutException as e:
        raise HTTPException(504, "الخدمة الداخلية لم ترد ضمن المهلة") from e
    except httpx.HTTPError as e:
        raise HTTPException(502, "تعذر الاتصال بالخدمة الداخلية") from e
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_response_headers(upstream.headers.items()),
        media_type=upstream.headers.get("content-type"),
    )


@router.api_route(
    "/api/edge/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def proxy_edge(
    path: str,
    request: Request,
    user: UserSchema = Depends(get_current_user),
) -> Response:
    """واجهة الويب/Flutter → JWT → platform → X-Agent-Token → edge-inference."""
    base = os.getenv("EDGE_INFERENCE_URL", "http://sahool-edge:8100")
    return await _proxy(request=request, user=user, base_url=base, path=path, timeout=120.0)


@router.api_route(
    "/api/soil/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def proxy_soil(
    path: str,
    request: Request,
    user: UserSchema = Depends(get_current_user),
) -> Response:
    """واجهة التربة → JWT → platform → X-Agent-Token + X-Tenant-Id → soil-service."""
    base = os.getenv("SOIL_SERVICE_URL", "http://sahool-soil-service:8000")
    return await _proxy(request=request, user=user, base_url=base, path=path, timeout=60.0)


@router.api_route(
    "/api/segmentation/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def proxy_segmentation(
    path: str,
    request: Request,
    user: UserSchema = Depends(get_current_user),
) -> Response:
    """واجهة تقطيع الحقل → JWT → platform → X-Agent-Token + X-Tenant-Id →
    field-segmentation. الهدف ثابت (لا SSRF). المسار اليدويّ حقيقيّ؛ auto/hybrid
    يردّ 503 صادق إن لم يُهيّأ نموذج (SAM2/GeoSAM)."""
    base = os.getenv("SEGMENTATION_URL", "http://sahool-field-segmentation:8000")
    return await _proxy(request=request, user=user, base_url=base, path=path, timeout=120.0)


@router.api_route(
    "/api/field-forms/{path:path}",
    methods=["GET", "POST"],
    include_in_schema=False,
)
async def proxy_field_forms(
    path: str,
    request: Request,
    user: UserSchema = Depends(get_current_user),
) -> Response:
    """GAP-FIELD-FORMS-01 §8.6 — تطبيق Flutter → JWT → platform → X-Field-Forms-Token
    + X-Tenant-Id → scout-ingest (/internal/field-forms/*). الهاتف لا يحمل توكن
    الخدمة ولا مفاتيح HMAC إطلاقًا: المنصّة تتحقّق من المستخدم ثمّ تحقن توكن القناة
    المخصّص خادميًّا. يُسمح بتنزيل النماذج وإرسالها فقط — إدارة التعريفات/النشر
    تبقى داخليّة (لا تمرّ عبر هذا المسار)."""
    # قائمة مسارات مغلقة: download/submissions فقط (الإدارة = publish/retire/assignments
    # تبقى /internal صرفة عبر توكن الخدمة، §8.6 — لا واجهة إدارة من الهاتف في هذه الشريحة).
    allowed = {"download", "submissions"}
    if path.strip("/") not in allowed:
        raise HTTPException(404, "مسار field-forms غير مكشوف عبر BFF")
    base = os.getenv("SCOUT_INGEST_URL", "http://sahool-scout-ingest:8000")
    return await _proxy(
        request=request,
        user=user,
        base_url=base,
        path=f"internal/field-forms/{path.strip('/')}",
        timeout=60.0,
        service_header=("X-Field-Forms-Token", _field_forms_token()),
        inject_actor=True,
    )
