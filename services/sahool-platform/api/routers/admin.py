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

from api.event_bus import dead_letter_summary
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()

# عتبة الموت (DLQ) لمسارات outbox المباشرة — مطابقة لافتراضيّ OutboxWorker.max_retries.
# صفّ ميّت = status='failed' AND retry_count >= هذه العتبة.
_OUTBOX_MAX_RETRIES = 5


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


# ─── outbox DLQ مباشر (TRUE backoff + فحص/إعادة جدولة على الأعمدة) ───
# مسارات تعمل مباشرةً على أعمدة event_outbox (status/retry_count/last_attempt_at)
# دون الاعتماد على دوالّ/views الـSQL المخصّصة — تكامل مع التراجع الأسّيّ الزمنيّ
# في OutboxWorker. التشكيل عبر dead_letter_summary النقيّة (قابلة للاختبار offline).


@router.get("/api/v1/admin/outbox/dead-letter")
async def admin_outbox_dead_letter(
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """فحص DLQ لِـoutbox: عدّ + عيّنة للصفوف الميّتة (status='failed' AND retry_count>=max).

    مُرشَّح بالمستأجِر (RLS على events عبر الـJOIN). الـSQL أدنويّ والتشكيل نقيّ
    (dead_letter_summary). بعد إصلاح السبب أعِد جدولتها عبر مسار requeue أدناه.
    """
    summary: dict = dead_letter_summary([])
    try:
        async with tenant_connection(user) as conn:
            recs = await conn.fetch(
                """SELECT o.outbox_id, o.event_id, o.nats_subject, o.retry_count,
                          o.last_error, o.last_attempt_at
                   FROM event_outbox o
                   JOIN events e ON e.event_id = o.event_id
                   WHERE o.status = 'failed' AND o.retry_count >= $1
                   ORDER BY o.last_attempt_at DESC NULLS LAST
                   LIMIT 500""",
                _OUTBOX_MAX_RETRIES,
            )
            summary = dead_letter_summary([dict(r) for r in recs])
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("فحص الأحداث الميّتة (outbox DLQ)", e) from e
    return {
        **summary,
        "note_ar": (
            "صفوف outbox استُنفدت محاولاتها (status='failed', retry_count>=max). "
            "بعد إصلاح السبب أعِد جدولتها عبر POST .../outbox/dead-letter/requeue. "
            "مراقبة: نبّه لو total>0."
        ),
    }


@router.post("/api/v1/admin/outbox/dead-letter/requeue")
async def admin_outbox_requeue_dead_letter(
    outbox_id: int | None = None,
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """يعيد جدولة صفوف outbox ميّتة → pending (retry_count=0, last_attempt_at=NULL).

    ``outbox_id`` محدّد ⇒ صفّ واحد، أو غيابه ⇒ كلّ الصفوف الميّتة (للمستأجِر).
    يجعل العامل يعيد محاولتها فوراً في الدورة التالية. يُرجع عدد الصفوف المُعادة.
    """
    try:
        async with tenant_connection(user) as conn:
            if outbox_id is not None:
                status = await conn.execute(
                    """UPDATE event_outbox o
                       SET status = 'pending', retry_count = 0,
                           last_attempt_at = NULL, last_error = NULL
                       FROM events e
                       WHERE e.event_id = o.event_id
                         AND o.outbox_id = $1
                         AND o.status = 'failed' AND o.retry_count >= $2""",
                    outbox_id,
                    _OUTBOX_MAX_RETRIES,
                )
            else:
                status = await conn.execute(
                    """UPDATE event_outbox o
                       SET status = 'pending', retry_count = 0,
                           last_attempt_at = NULL, last_error = NULL
                       FROM events e
                       WHERE e.event_id = o.event_id
                         AND o.status = 'failed' AND o.retry_count >= $1""",
                    _OUTBOX_MAX_RETRIES,
                )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إعادة جدولة صفوف outbox الميّتة", e) from e
    try:
        requeued = int(str(status).rsplit(" ", 1)[-1])
    except (ValueError, IndexError):
        requeued = 0
    if outbox_id is not None and requeued == 0:
        raise HTTPException(status_code=404, detail="لا صفّ outbox ميّت بهذا المعرّف (أو غير فاشل)")
    return {"requeued_count": requeued, "outbox_id": outbox_id}
