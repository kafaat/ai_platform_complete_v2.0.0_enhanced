"""api/routers/field_priority_queue.py — Field/Farm Priority Queue façade (UI-20).

يوفّر واجهات قراءة مستقرة للواجهة:

* GET /api/v1/fields/{field_id}/priority-queue
* GET /api/v1/farms/{farm_id}/priority-queue

القاعدة الحاكمة: لا تُصنَّع أولويات. العناصر تأتي فقط من جداول تشغيلية موجودة
فعلياً مثل ``alerts`` و``field_tasks``. عند غياب جدول اختياري أو فشل جزء من القراءة
تُعاد النتيجة الجزئية مع ``degraded=true`` وسبب عربي واضح، ولا تُضاف عناصر بديلة.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_TYPE_RANK = {"alert": 0, "task": 1, "recommendation": 2, "weather_window": 3, "imagery": 4}


def _iso(value: Any) -> str | None:
    return (
        value.isoformat()
        if hasattr(value, "isoformat")
        else (str(value) if value is not None else None)
    )


def _task_title_ar(task_type: str | None) -> str:
    labels = {
        "irrigation": "مهمة ري",
        "spray": "مهمة رش",
        "scouting": "مهمة تفتيش",
        "fertilization": "مهمة تسميد",
        "harvest": "مهمة حصاد",
    }
    return labels.get(str(task_type or "").lower(), f"مهمة تشغيلية: {task_type or 'غير محددة'}")


def _priority_from_task(value: Any) -> str:
    try:
        p = int(value or 3)
    except Exception:  # noqa: BLE001 — قيمة تالفة من القاعدة لا تكسر القراءة
        p = 3
    if p <= 1:
        return "high"
    if p == 2:
        return "medium"
    return "low"


def _sort_key(item: dict) -> tuple[int, int, str]:
    return (
        _SEVERITY_RANK.get(str(item.get("severity") or "medium"), 2),
        _TYPE_RANK.get(str(item.get("type") or ""), 9),
        str(item.get("due_at") or item.get("created_at") or ""),
    )


def _shape_alert(row) -> dict:
    return {
        "id": str(row["alert_id"]),
        "type": "alert",
        "field_id": row.get("field_id"),
        "title_ar": row.get("title_ar") or "تنبيه نشط",
        "description_ar": row.get("message_ar"),
        "severity": row.get("severity") or "medium",
        "created_at": _iso(row.get("created_at")),
        "reasons": ["تنبيه نشط من جدول alerts"],
        "action": {"kind": "open_alert", "alert_id": str(row["alert_id"])},
    }


def _shape_task(row) -> dict:
    return {
        "id": str(row["task_id"]),
        "type": "task",
        "field_id": row.get("field_id"),
        "title_ar": _task_title_ar(row.get("task_type")),
        "severity": _priority_from_task(row.get("priority")),
        "due_at": _iso(row.get("recommended_date")),
        "status": row.get("status"),
        "reasons": ["مهمة مفتوحة من جدول field_tasks"],
        "action": {"kind": "open_task", "task_id": str(row["task_id"])},
    }


async def _optional_fetch(conn, query: str, *args) -> tuple[list, str | None]:
    """قراءة اختيارية: فشلها لا يصنع عناصر ولا يُسقط الصفحة."""
    try:
        rows = await conn.fetch(query, *args)
        return list(rows), None
    except Exception as exc:  # noqa: BLE001 — جدول اختياري غائب/هجرة ناقصة
        return [], f"تعذّر قراءة مصدر اختياري ({type(exc).__name__})"


async def _assert_farm_in_tenant(conn, farm_id: str) -> None:
    exists = await conn.fetchval("SELECT 1 FROM farms WHERE farm_id = $1", farm_id)
    if not exists:
        raise HTTPException(status_code=404, detail="المزرعة غير موجودة ضمن هذا المستأجِر")


@router.get("/api/v1/fields/{field_id}/priority-queue")
async def field_priority_queue(
    field_id: str,
    limit: int = 20,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """أولويات تشغيلية لحقل واحد من مصادر حقيقية فقط.

    لا ترتّب أو تضيف عناصر من الواجهة؛ كل عنصر يعود من ``alerts`` أو
    ``field_tasks``. عند تعذر أحد المصدرين تعود قائمة جزئية مع ``degraded=true``.
    """
    items: list[dict] = []
    warnings: list[str] = []
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            alert_rows, warning = await _optional_fetch(
                conn,
                """
                SELECT alert_id, field_id, alert_type, severity, title_ar, message_ar, created_at
                FROM alerts
                WHERE field_id = $1 AND status = 'active'
                ORDER BY created_at DESC
                LIMIT $2
                """,
                field_id,
                max(1, min(int(limit or 20), 100)),
            )
            if warning:
                warnings.append(warning)
            task_rows, warning = await _optional_fetch(
                conn,
                """
                SELECT task_id, field_id, task_type, priority, status, recommended_date, created_at
                FROM field_tasks
                WHERE field_id = $1 AND status IN ('pending', 'in_progress')
                ORDER BY priority ASC, recommended_date ASC NULLS LAST, created_at DESC
                LIMIT $2
                """,
                field_id,
                max(1, min(int(limit or 20), 100)),
            )
            if warning:
                warnings.append(warning)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — فشل أساسي في DB/اتصال/RLS
        raise _db_unavailable("قراءة أولويات الحقل", exc) from exc

    items.extend(_shape_alert(r) for r in alert_rows)
    items.extend(_shape_task(r) for r in task_rows)
    items = sorted(items, key=_sort_key)[: max(1, min(int(limit or 20), 100))]
    return {
        "scope": "field",
        "field_id": field_id,
        "items": items,
        "degraded": bool(warnings),
        "warning_ar": "؛ ".join(warnings) if warnings else None,
        "note_ar": "تُبنى الأولوية من بيانات تشغيلية مخزنة فقط؛ لا توجد عناصر مصطنعة.",
    }


@router.get("/api/v1/farms/{farm_id}/priority-queue")
async def farm_priority_queue(
    farm_id: str,
    limit: int = 30,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """أولويات تشغيلية على مستوى مزرعة من الحقول التابعة لها فقط."""
    items: list[dict] = []
    warnings: list[str] = []
    try:
        async with tenant_connection(user) as conn:
            await _assert_farm_in_tenant(conn, farm_id)
            alert_rows, warning = await _optional_fetch(
                conn,
                """
                SELECT a.alert_id, a.field_id, a.alert_type, a.severity, a.title_ar, a.message_ar, a.created_at
                FROM alerts a
                JOIN fields f ON f.field_id = a.field_id
                WHERE f.farm_id = $1 AND a.status = 'active'
                ORDER BY a.created_at DESC
                LIMIT $2
                """,
                farm_id,
                max(1, min(int(limit or 30), 100)),
            )
            if warning:
                warnings.append(warning)
            task_rows, warning = await _optional_fetch(
                conn,
                """
                SELECT t.task_id, t.field_id, t.task_type, t.priority, t.status, t.recommended_date, t.created_at
                FROM field_tasks t
                JOIN fields f ON f.field_id = t.field_id
                WHERE f.farm_id = $1 AND t.status IN ('pending', 'in_progress')
                ORDER BY t.priority ASC, t.recommended_date ASC NULLS LAST, t.created_at DESC
                LIMIT $2
                """,
                farm_id,
                max(1, min(int(limit or 30), 100)),
            )
            if warning:
                warnings.append(warning)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("قراءة أولويات المزرعة", exc) from exc

    items.extend(_shape_alert(r) for r in alert_rows)
    items.extend(_shape_task(r) for r in task_rows)
    items = sorted(items, key=_sort_key)[: max(1, min(int(limit or 30), 100))]
    return {
        "scope": "farm",
        "farm_id": farm_id,
        "items": items,
        "degraded": bool(warnings),
        "warning_ar": "؛ ".join(warnings) if warnings else None,
        "note_ar": "تُبنى الأولوية من تنبيهات ومهام مخزنة فقط؛ لا توجد عناصر مصطنعة.",
    }
