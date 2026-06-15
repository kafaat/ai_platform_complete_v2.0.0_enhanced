"""api/routers/admin.py — حوكمة الأحداث الفاشلة (Admin / Event DLQ)
======================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.
العزل بالمستأجِر (RLS على events) ومنطق requeue لم يُمسّا.

الاعتماديّات المشتركة (التبعيات/الأذونات/الاتّصال/المساعِدات) تبقى مُعرَّفة في
``api.main`` وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات
الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.get("/api/v1/admin/events/dead-letter")
async def admin_events_dead_letter(
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """حوكمة الأحداث الفاشلة (DLQ): يعرض أحداث event_outbox الميّتة + تفاصيلها.

    فوق v_event_dead_letter (v48). مُرشَّح بالمستأجِر (RLS على events) — كلّ مستأجِر
    أحداثه الفاشلة. (عرض ops عابر المستأجرين = شأن superuser منفصل، مؤجَّل.)
    """
    rows: list = []
    try:
        async with tenant_connection(user) as conn:
            recs = await conn.fetch(
                """SELECT outbox_id, event_id::text, nats_subject, retry_count,
                          last_error, last_attempt_at, created_at,
                          event_type, entity_type, entity_id, occurred_at
                   FROM v_event_dead_letter ORDER BY created_at DESC LIMIT 500"""
            )
            rows = [
                {
                    "outbox_id": r["outbox_id"],
                    "event_id": r["event_id"],
                    "nats_subject": r["nats_subject"],
                    "retry_count": r["retry_count"],
                    "last_error": r["last_error"],
                    "last_attempt_at": r["last_attempt_at"].isoformat()
                    if r["last_attempt_at"]
                    else None,
                    "event_type": r["event_type"],
                    "entity_type": r["entity_type"],
                    "entity_id": r["entity_id"],
                }
                for r in recs
            ]
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة الأحداث الميّتة (DLQ)", e) from e
    return {
        "dead_letter": rows,
        "total": len(rows),
        "note_ar": (
            "أحداث فشل نشرها إلى NATS بعد استنفاد المحاولات. بعد إصلاح السبب "
            "(مثلاً NATS متوقّف) أعِد جدولتها عبر requeue. مراقبة: نبّه لو total>0."
        ),
    }


@router.post("/api/v1/admin/events/dead-letter/{outbox_id}/requeue")
async def admin_requeue_dead_letter(
    outbox_id: int,
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """يعيد جدولة حدث ميّت واحد → pending (بعد إصلاح السبب). فوق requeue_dead_letter (v48)."""
    try:
        async with tenant_connection(user) as conn:
            requeued = await conn.fetchval("SELECT requeue_dead_letter($1)", outbox_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إعادة جدولة حدث ميّت", e) from e
    if not requeued:
        raise HTTPException(status_code=404, detail="لا حدث ميّت بهذا المعرّف (أو غير فاشل)")
    return {"outbox_id": outbox_id, "requeued": True}


@router.post("/api/v1/admin/events/dead-letter/requeue-all")
async def admin_requeue_all_dead_letter(
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """يعيد جدولة كلّ الأحداث الميّتة (تشغيل ops بعد إصلاح NATS). فوق requeue_all_dead_letter."""
    try:
        async with tenant_connection(user) as conn:
            count = await conn.fetchval("SELECT requeue_all_dead_letter()")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إعادة جدولة كلّ الأحداث الميّتة", e) from e
    return {"requeued_count": int(count or 0)}
