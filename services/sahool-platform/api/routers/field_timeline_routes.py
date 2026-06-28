"""api/routers/field_timeline_routes.py — مسارات الخطّ الزمنيّ والتاريخ (Timeline & History) للحقل.

شريحة مُستخرَجة من ``api/routers/fields.py`` (تفكيك تدريجيّ محفوظ-السلوك للملفّ الأكبر):
نُقلت المعالِجات الثلاث للخطّ الزمنيّ والتاريخ حرفيّاً — بنفس المسارات/الطلبات/المخرجات/
الأذونات/مخطّط OpenAPI — دون أيّ تغيير في السلوك:

  • ``POST /api/v1/fields/{field_id}/timeline``          → ``field_timeline``
  • ``GET  /api/v1/fields/{field_id}/history``           → ``field_history``
  • ``GET  /api/v1/fields/{field_id}/unified-timeline``  → ``field_unified_timeline``

التسجيل تلقائيّ عبر ``api.router_registry.register_routers`` (حلقة ``pkgutil`` على
``api/routers/`` — أيّ وحدة تُصدّر ``router`` تُضمّ). بما أنّ المسارات نُقلت (لا نُسخت)
من ``fields.py`` فلا تكرار (مسار، طريقة).

الاعتماديّات: الرموز المشتركة تُستورَد من مصادرها الأصليّة نفسها كما في ``fields.py``
(``assemble_timeline`` من ``api.field_timeline``؛ والتبعيّات/النماذج/المساعِدات من
``api.main``). لتفادي الاستيراد الدائريّ: ``api.main`` يُستورَد هنا، وحلقة التسجيل
تُنفَّذ في نهاية ``main.py`` بعد اكتمال تعريف كلّ تلك الرموز.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.field_timeline import assemble_timeline
from api.main import (
    _DB_POOL,
    TimelineRequest,
    UserSchema,
    _issue_tags_from_event,
    get_current_user,
    tenant_connection,
)

router = APIRouter()


@router.post("/api/v1/fields/{field_id}/timeline")
def field_timeline(
    field_id: str,
    req: TimelineRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يبني الخطّ الزمني للحقل (مُصنّف + مرتّب + بإحصاءات الفئات).

    ملاحظة: يأخذ الأحداث في الـrequest. النسخة التي تجلب من events table
    تحتاج PostgreSQL — غير مُفعَّلة بعد.
    """
    tl = assemble_timeline(
        field_id,
        req.events,
        newest_first=req.newest_first,
        category_filter=req.category_filter,
    )
    return tl.to_dict()


@router.get("/api/v1/fields/{field_id}/history")
async def field_history(
    field_id: str,
    limit: int = 200,
    user: UserSchema = Depends(get_current_user),
):
    """السياق التاريخي للحقل: أحداثه + القضايا المتكرّرة (farm memory).

    يجلب من events table عبر tenant_connection (RLS — كلّ مستأجر أحداثه فقط).
    يُغذّي memory_adapter في حلقة القرار (Runtime Cohesion). صدق: عند تعطّل
    القاعدة يُرجِع events فارغة (لا تاريخ مخترَع) ويُعلن السبب.
    """
    if _DB_POOL is None:
        return {
            "field_id": field_id,
            "events": [],
            "total_events": 0,
            "note_ar": "القاعدة غير مفعّلة (DATABASE_URL) — لا تاريخ حيّ",
        }
    out_events: list[dict] = []
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                """
                SELECT event_id, event_type, payload, occurred_at
                FROM events
                WHERE entity_type = 'field' AND entity_id = $1
                ORDER BY occurred_at DESC
                LIMIT $2
                """,
                field_id,
                max(1, min(limit, 1000)),  # قصّ [1..1000]: limit≤0 يرمي/يُفرغ بلا داعٍ
            )
        for r in rows:
            payload = r["payload"] if isinstance(r["payload"], dict) else {}
            out_events.append(
                {
                    "event_id": str(r["event_id"]),
                    "event_type": r["event_type"],
                    "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else "",
                    "issue_tags": _issue_tags_from_event(r["event_type"], payload),
                }
            )
    except Exception as e:  # noqa: BLE001 — صدق: نُعلن الفشل لا نخترع تاريخاً
        return {
            "field_id": field_id,
            "events": [],
            "total_events": 0,
            "error": f"تعذّر جلب التاريخ: {e}",
        }
    return {"field_id": field_id, "events": out_events, "total_events": len(out_events)}


@router.get("/api/v1/fields/{field_id}/unified-timeline")
async def field_unified_timeline(
    field_id: str,
    limit: int = 200,
    newest_first: bool = True,
    category: str | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """الخطّ الزمنيّ الموحّد للحقل: يدمج أحداثه عبر كلّ أنواع الكيانات.

    على عكس ``/history`` (يجلب ``entity_type='field'`` فقط)، يجمع هنا دورة الحياة
    والأنشطة والتنبيهات والتوصيات لحقلٍ واحد — سواء كان ``field_id`` هو ``entity_id``
    أو داخل ``payload->>'field_id'`` — ويمرّ بـ``assemble_timeline`` (تصنيف+فرز+إحصاءات)
    عبر ``tenant_connection`` (RLS — كلّ مستأجر أحداثه فقط). صدق: عند تعطّل القاعدة
    يُرجِع خطّاً فارغاً ويُعلن السبب (لا تاريخ مخترَع).
    """
    if _DB_POOL is None:
        return {
            "field_id": field_id,
            "events": [],
            "total_events": 0,
            "note_ar": "القاعدة غير مفعّلة (DATABASE_URL) — لا تاريخ حيّ",
        }
    raw: list[dict] = []
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                """
                SELECT event_id, event_type, payload, actor_id, occurred_at
                FROM events
                WHERE entity_id = $1 OR payload->>'field_id' = $1
                ORDER BY occurred_at DESC
                LIMIT $2
                """,
                field_id,
                max(1, min(limit, 1000)),
            )
        for r in rows:
            payload = r["payload"] if isinstance(r["payload"], dict) else {}
            raw.append(
                {
                    "event_id": str(r["event_id"]),
                    "event_type": r["event_type"],
                    "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else "",
                    "payload": payload,
                    "actor_id": r["actor_id"],
                }
            )
    except Exception as e:  # noqa: BLE001 — صدق: نُعلن الفشل لا نخترع تاريخاً
        return {
            "field_id": field_id,
            "events": [],
            "total_events": 0,
            "error": f"تعذّر جلب الخطّ الزمنيّ: {e}",
        }
    tl = assemble_timeline(
        field_id,
        raw,
        newest_first=newest_first,
        category_filter=[category] if category else None,
    )
    return tl.to_dict()
