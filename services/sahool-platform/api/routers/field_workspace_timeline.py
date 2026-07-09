"""api/routers/field_workspace_timeline.py — Field Workspace unified timeline façade (UI-31).

يمتلك هذا الراوتر قراءة الخطّ الزمني الموحّد للحقل:

* GET /api/v1/fields/{field_id}/unified-timeline

الهدف هو إخراج آخر route خاص بـ Field Workspace من ``routers/fields.py`` ومنع
تحوّل ملف الحقول إلى مجمّع لمسارات سطح التشغيل. المصدر الوحيد هو جدول ``events``
ضمن سياق المستأجر؛ لا تُصنّع الواجهة أو الراوتر أحداثاً بديلة عند غياب البيانات.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from api.field_timeline import assemble_timeline
from api.main import (
    _DB_POOL,
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.get("/api/v1/fields/{field_id}/unified-timeline")
async def field_unified_timeline_facade(
    field_id: str,
    limit: int = Query(200, ge=1, le=1000),
    newest_first: bool = True,
    category: str | None = None,
    season_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """خط زمني موحّد مملوك للـ backend ويقرأ أحداثاً حقيقية فقط.

    ``season_id`` فلتر اختياري: إن وُجد، تُقرأ الأحداث المرتبطة بالموسم من payload.
    عند تعطّل DB تُعاد حالة فارغة مُعلنة بدلاً من أحداث مصطنعة.
    """
    if _DB_POOL is None:
        return {
            "field_id": field_id,
            "season_id": season_id,
            "events": [],
            "total_events": 0,
            "degraded": True,
            "note_ar": "القاعدة غير مفعّلة (DATABASE_URL) — لا تاريخ حيّ",
        }

    raw: list[dict[str, Any]] = []
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            if season_id:
                rows = await conn.fetch(
                    """
                    SELECT event_id, event_type, payload, actor_id, occurred_at
                    FROM events
                    WHERE (entity_id = $1 OR payload->>'field_id' = $1)
                      AND payload->>'season_id' = $2
                    ORDER BY occurred_at DESC
                    LIMIT $3
                    """,
                    field_id,
                    season_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT event_id, event_type, payload, actor_id, occurred_at
                    FROM events
                    WHERE entity_id = $1 OR payload->>'field_id' = $1
                    ORDER BY occurred_at DESC
                    LIMIT $2
                    """,
                    field_id,
                    limit,
                )
        for row in rows:
            payload = row["payload"] if isinstance(row["payload"], dict) else {}
            raw.append(
                {
                    "event_id": str(row["event_id"]),
                    "event_type": row["event_type"],
                    "occurred_at": row["occurred_at"].isoformat() if row["occurred_at"] else "",
                    "payload": payload,
                    "actor_id": row["actor_id"],
                }
            )
    except Exception as exc:  # noqa: BLE001 — صدق: نُعلن الفشل ولا نختلق أحداثاً.
        return {
            "field_id": field_id,
            "season_id": season_id,
            "events": [],
            "total_events": 0,
            "degraded": True,
            "error": f"تعذّر جلب الخطّ الزمنيّ: {exc}",
        }

    timeline = assemble_timeline(
        field_id,
        raw,
        newest_first=newest_first,
        category_filter=[category] if category else None,
    ).to_dict()
    timeline["season_id"] = season_id
    timeline["degraded"] = False
    return timeline
