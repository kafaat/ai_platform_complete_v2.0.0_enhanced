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

from fastapi import APIRouter, Depends

from api.edge_models import EdgeSyncRequest
from api.main import UserSchema, get_current_user, tenant_connection

router = APIRouter()


@router.post("/api/v1/edge/sync")
@router.post("/v1/edge/sync")
async def edge_sync_receive(
    req: EdgeSyncRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يستقبل نتيجة من جهاز edge ويكتبها مع منع التكرار.

    Hardening: ON CONFLICT على idempotency_key → إعادة الإرسال بعد انقطاع
    الشبكة لا تُكرّر الصفّ. الهويّة من التوكن لا الجسم (أمان)."""
    import json as _json

    async with tenant_connection(user) as conn:
        row = await conn.fetchrow(
            """INSERT INTO edge_results
                 (field_id, tenant_id, result_type, device, offline_mode,
                  synced, result_data, idempotency_key, occurred_at)
               VALUES ($1, $2::uuid, $3, $4, true, true, $5::jsonb, $6,
                       COALESCE($7::timestamptz, NOW()))
               ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
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
    # row=None يعني التكرار رُفض (نجح سابقاً) — نُرجع نجاحاً (idempotent)
    return {
        "status": "stored" if row else "duplicate_ignored",
        "id": row["id"] if row else None,
        "idempotency_key": req.idempotency_key,
    }
