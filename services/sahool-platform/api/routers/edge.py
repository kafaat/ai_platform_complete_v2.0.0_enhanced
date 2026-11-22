"""api/routers/edge.py — استقبال مزامنة الحافة (Edge Sync Ingest)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router`` (بمسارَيها
المُسجَّلَين معاً: /api/v1/edge/sync و/v1/edge/sync).

النموذج ``EdgeSyncRequest`` نُقل إلى ``api.edge_models`` ويُستورَد من هناك (نمط
B1). لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from core.canonical_schemas import UserRole
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from api.edge_models import (
    PROVENANCE_RESULT_TYPES,
    EdgeSyncRequest,
    provenance_rows,
    read_detection_provenance,
    record_detection_provenance,
)
from api.main import UserSchema, _assert_field_in_tenant, get_current_user, tenant_connection
from api.service_token_auth import EDGE_SYNC, _require_service_token, verify_channel_tenant

router = APIRouter()


def edge_sync_actor(
    request: Request,
    authorization: str | None = Header(None),
) -> UserSchema:
    """Who the edge result is written for (W0-07, finding scout-1).

    * **Service mode** — the edge sends ``X-Agent-Token`` + ``X-Service-Name`` + ``X-Tenant-Id`` +
      ``X-Tenant-Assertion`` (``EDGE_SYNC_TENANT_ASSERTION_KEY``, held by the edge alone). The
      tenant is the one the edge carried in that observation's envelope, so each result lands
      under its own tenant instead of under the single tenant of a shared ``EDGE_SYNC_TOKEN``. The field is still checked inside that tenant.
    * **Bearer mode** — a user JWT, as before: the tenant comes from the token.

    A request that starts service mode never falls back to the bearer: a bad assertion is a refusal.
    Synchronous on purpose: FastAPI runs it in the threadpool (Redis replay check, JWT revocation).
    """
    headers = request.headers
    if "x-tenant-assertion" in headers or "x-service-name" in headers:
        _require_service_token(headers.get("x-agent-token"))
        tenant = headers.get("x-tenant-id") or ""
        verify_channel_tenant(EDGE_SYNC, request, tenant)
        return UserSchema(
            user_id=f"service:{headers.get('x-service-name')}",
            tenant_id=tenant,
            role=UserRole.VIEWER,
            name_ar="",
        )
    return get_current_user(authorization, request)


@router.post("/api/v1/edge/sync")
@router.post("/v1/edge/sync")
async def edge_sync_receive(
    req: EdgeSyncRequest,
    user: UserSchema = Depends(edge_sync_actor),
):
    """يستقبل نتيجة من جهاز edge ويكتبها مع منع التكرار.

    Hardening: ON CONFLICT على idempotency_key → إعادة الإرسال بعد انقطاع
    الشبكة لا تُكرّر الصفّ. الهويّة من التوكن لا الجسم (أمان).

    CP997-05 (Copilot على #997): كان الفهرسُ الفريد `uq_edge_idempotency` (v9) **عالميّاً** على
    المفتاح بينما بحثُ الصفّ القائم أدناه مقيّدٌ بالمستأجِر، فمفتاحُ مستأجِرٍ آخر كان يصطدم ثمّ لا
    يُعثَر عليه فيُرفَع 409 على حدثٍ صالح. v241 جعل الفهرسَ `(tenant_id, idempotency_key)`،
    والهدفُ هنا يطابقه — والإعادةُ المطابقة وحدها نجاحٌ idempotent."""
    import json as _json

    # نسبُ الكشف (v239): يُتحقَّق منه **قبل** أيّ كتابة — كتلةُ نسبٍ مشوَّهة 422 لا صفٌّ نصفُ مُثبَت.
    try:
        provenance = provenance_rows(req.type, req.data)
    except ValueError as exc:
        raise HTTPException(422, f"detection_provenance_invalid:{exc}") from exc
    stored_provenance: list[dict] | None = None

    async with tenant_connection(user) as conn:
        await _assert_field_in_tenant(conn, req.field_id)
        row = await conn.fetchrow(
            """INSERT INTO edge_results
                 (field_id, tenant_id, result_type, device, offline_mode,
                  synced, result_data, idempotency_key, occurred_at)
               VALUES ($1, $2::uuid, $3, $4, true, true, $5::jsonb, $6,
                       $7::timestamptz)
               ON CONFLICT (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL
               DO NOTHING
               RETURNING id""",
            req.field_id,
            str(user.tenant_id),
            req.type,
            req.device_id,
            _json.dumps(req.data, ensure_ascii=False),
            req.idempotency_key,
            req.occurred_at,
        )
        if row is None:
            existing = await conn.fetchrow(
                "SELECT id, field_id, result_type, device, result_data, occurred_at FROM edge_results "
                "WHERE idempotency_key=$1 AND tenant_id=$2::uuid",
                req.idempotency_key,
                str(user.tenant_id),
            )
            payload = existing["result_data"] if existing else None
            if isinstance(payload, str):
                payload = _json.loads(payload)
            if (
                not existing
                or existing["field_id"] != req.field_id
                or existing["device"] != req.device_id
                or existing["result_type"] != req.type
                or not same_json(payload, req.data)
                or existing["occurred_at"] != req.occurred_at
            ):
                raise HTTPException(409, "edge_idempotency_conflict")
        else:
            # المعاملةُ نفسُها: لا صفَّ كشفٍ مُخزَّناً بلا صفّ نسبه.
            await record_detection_provenance(
                conn,
                tenant_id=str(user.tenant_id),
                edge_result_id=row["id"],
                rows=provenance,
            )
        if req.type in PROVENANCE_RESULT_TYPES:
            stored_provenance = await read_detection_provenance(
                conn, row["id"] if row else existing["id"]
            )
    receipt = {
        "status": "stored" if row else "duplicate_ignored",
        "id": row["id"] if row else existing["id"],
        "idempotency_key": req.idempotency_key,
    }
    if stored_provenance is not None:
        # قراءةُ النسب كما خُزِّن (RLS المستأجر)، في الإيصال وفي إعادة الإرسال المطابقة.
        receipt["provenance"] = stored_provenance
    # Only an identical, tenant-visible event counts as successful replay.
    return receipt


def same_json(stored, sent) -> bool:
    """Equality of two JSON values with PostgreSQL ``jsonb`` semantics (measured on PG16).

    The replay check compares the stored ``result_data`` with the resent body. Python's ``==``
    treats ``True == 1`` and ``False == 0``, so a replay that changed a boolean into a number was
    answered ``duplicate_ignored``: the device got a success receipt for a change that was never
    stored. In ``jsonb`` a boolean never equals a number; numbers compare by value (``1`` equals
    ``1.0``), object key order does not matter, array order does.
    """
    if isinstance(stored, bool) or isinstance(sent, bool):
        return type(stored) is type(sent) and stored == sent
    if isinstance(stored, dict) and isinstance(sent, dict):
        return stored.keys() == sent.keys() and all(same_json(stored[k], sent[k]) for k in stored)
    if isinstance(stored, list) and isinstance(sent, list):
        return len(stored) == len(sent) and all(
            same_json(a, b) for a, b in zip(stored, sent, strict=True)
        )
    if isinstance(stored, (int, float)) and isinstance(sent, (int, float)):
        return stored == sent
    return type(stored) is type(sent) and stored == sent
