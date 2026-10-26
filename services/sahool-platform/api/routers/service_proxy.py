"""api/routers/service_proxy.py — بوابات آمنة للخدمات الداخلية التي تحتاج X-Agent-Token.

الغرض: تفعيل وظائف الواجهة دون كشف SAHOOL_AGENT_TOKEN للمتصفح/Flutter.
المستخدم يقدّم JWT عادي؛ sahool-platform يتحقق من المستخدم ثم يحقن توكن الخدمة
و X-Tenant-Id قبل تمرير الطلب إلى edge/soil.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    get_current_user,
    require_permission,
    tenant_connection,
)

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

# Public BFF contract. Internal governance/administration endpoints are not
# automatically exposed when a new soil-service router is registered.
_SOIL_ROUTES = (
    (r"(?:health|healthz|readyz)", "GET", Permission.SETTINGS_VIEW),
    (r"v1/soil/readings/[^/%\\?#]+", "GET", Permission.OBSERVATION_VIEW),
    (
        r"v1/fields/[^/%\\?#]+/soil/(?:observations|profile|profile/history|closed-loop)",
        "GET",
        Permission.OBSERVATION_VIEW,
    ),
    (r"v1/soil/(?:ingest|observations)", "POST", Permission.OBSERVATION_RECORD),
    (r"v1/fields/[^/%\\?#]+/soil/evidence", "POST", Permission.OBSERVATION_RECORD),
    (r"v1/fields/[^/%\\?#]+/soil/profile/rebuild", "POST", Permission.OBSERVATION_RECORD),
)


# edge-inference: only the two inference calls the apps make, plus read-only
# probes. v1/sync/trigger (flushes the shared EDGE_SYNC_TOKEN queue) and /metrics
# stay internal; anything not listed is 404 before a service token is attached.
_EDGE_ROUTES = (
    (r"(?:healthz|readyz|capabilities)", "GET", Permission.SETTINGS_VIEW),
    (r"v1/inference/(?:pest-detect|yield-estimate)", "POST", Permission.OBSERVATION_RECORD),
)
# Inference results are synced to the platform under the caller-supplied field_id.
_EDGE_FIELD_BOUND_ROUTES = frozenset({"v1/inference/pest-detect", "v1/inference/yield-estimate"})

# field-segmentation: the boundary suggestion used while creating a field.
_SEGMENTATION_ROUTES = (
    (r"(?:health|healthz|readyz)", "GET", Permission.SETTINGS_VIEW),
    (r"v1/segment", "POST", Permission.FIELD_CREATE),
)


def _authorize_path(path: str, method: str, user: UserSchema, routes, label: str) -> str:
    path = path.removesuffix("/")
    not_exposed = f"مسار {label} غير مكشوف عبر BFF"
    if any(segment in {".", ".."} for segment in path.split("/")):
        raise HTTPException(404, not_exposed)
    matched = [
        (verb, permission) for pattern, verb, permission in routes if re.fullmatch(pattern, path)
    ]
    if not matched:
        raise HTTPException(404, not_exposed)
    for verb, permission in matched:
        if method.upper() == verb:
            # Reuse the platform's denial audit and RBAC; user was authenticated
            # by get_current_user before this function receives it.
            require_permission(permission)(user)
            return path
    raise HTTPException(
        405,
        "method not allowed",
        headers={"Allow": ", ".join(sorted({verb for verb, _ in matched}))},
    )


def _authorize_soil_path(path: str, method: str, user: UserSchema) -> str:
    return _authorize_path(path, method, user, _SOIL_ROUTES, "التربة")


async def _assert_form_field_in_tenant(request: Request, user: UserSchema) -> None:
    """The edge writes results under the form's field_id; refuse a field outside
    the caller's tenant before the shared service token is attached."""
    await request.body()  # cache the raw bytes so _proxy forwards exactly what was checked
    form = await request.form()
    try:
        values = form.getlist("field_id")
    finally:
        await form.close()
    if len(values) != 1 or not isinstance(values[0], str) or not values[0]:
        raise HTTPException(422, "field_id مطلوب مرّةً واحدة")
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, values[0])
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — cannot prove ownership ⇒ fail closed
        raise _db_unavailable("إثبات ملكيّة الحقل", e) from e


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
    path = _authorize_path(path, request.method, user, _EDGE_ROUTES, "الحافة")
    if path in _EDGE_FIELD_BOUND_ROUTES:
        await _assert_form_field_in_tenant(request, user)
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
    path = _authorize_soil_path(path, request.method, user)
    base = os.getenv("SOIL_SERVICE_URL", "http://sahool-soil-service:8000")
    return await _proxy(
        request=request, user=user, base_url=base, path=path, timeout=60.0, inject_actor=True
    )


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
    path = _authorize_path(path, request.method, user, _SEGMENTATION_ROUTES, "التقطيع")
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
