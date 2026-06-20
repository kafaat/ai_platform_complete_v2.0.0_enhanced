"""api/routers/operations.py — تلخيص تشغيليّ لجدار مركز العمليّات (قراءة فقط، P1).

نقطة واحدة محروسة بعلم ``FEATURE_OPERATIONS_WALL`` (مُطفأة افتراضاً ⇒ 404، نمط
``decision_dispatch``):

  • ``GET /api/v1/operations/summary`` — تلخيص تجميعيّ للمستأجِر (معزول RLS): عدد
    الحقول، التنبيهات النشطة مُجمَّعة بالخطورة (info/warning/critical)، عدد المعدّات
    والأجهزة، عدد القرارات المُدامة (decision_record)، حالة الريّ (صمّامات/جداول)،
    وآخر نشاط. كلّها COUNT/aggregation عبر ``tenant_connection``.

**الصدق**: أعداد حقيقيّة من القاعدة فقط. كلّ استعلام فرعيّ **best-effort** — فشل
أحدها (جدول غائب/هجرة غير مطبّقة) يُعيد ``None`` لذلك المصدر وحده ولا يُفشِل الكلّ؛
الطبقة النقيّة ``shape_operations_summary`` تشكّله 0/None مع ``note_ar`` صريح (لا
تلفيق). لا بيانات طقس خارجيّة هنا — تجلبها الواجهة من نقطتها. 503 فقط إن تعذّر فتح
اتّصال المستأجِر أصلاً (القاعدة غير متاحة كليّاً).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.operations_summary import shape_operations_summary

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}


def _operations_wall_enabled() -> bool:
    """هل ميزة جدار مركز العمليّات مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ)."""
    return os.getenv("FEATURE_OPERATIONS_WALL", "").strip().lower() in _TRUTHY


async def _scalar(conn, sql: str, *args) -> int | None:
    """ينفّذ استعلام عدّ تجميعيّ best-effort — يعيد int أو None عند تعذّره.

    أيّ خطأ (جدول غائب، هجرة غير مطبّقة، …) يُبتلع إلى None ليُوسَم لاحقاً صراحةً —
    فشل مصدر واحد لا يُفشِل التلخيص كلّه (الصدق: لا تلفيق، لا انهيار).
    """
    try:
        val = await conn.fetchval(sql, *args)
    except Exception:  # noqa: BLE001 — مصدر غائب ⇒ None (يُوسَم في الطبقة النقيّة)
        return None
    return int(val) if val is not None else 0


async def _alerts_by_severity(conn) -> dict[str, int] | None:
    """عدّ التنبيهات النشطة مُجمَّعاً بالخطورة best-effort — None عند تعذّر الجدول."""
    try:
        rows = await conn.fetch(
            "SELECT severity, COUNT(*) AS count FROM alerts "
            "WHERE status = 'active' GROUP BY severity"
        )
    except Exception:  # noqa: BLE001 — جدول غائب/هجرة غير مطبّقة ⇒ None
        return None
    return {str(r["severity"]): int(r["count"] or 0) for r in rows}


async def _last_activity(conn) -> str | None:
    """آخر نشاط (ISO) عبر المصادر المُدامة best-effort — None إن تعذّر/غاب الكلّ.

    يأخذ أحدث ``created_at`` عبر التنبيهات والقرارات المُدامة (مصدران مُتاحان دائماً
    في المسار الحرج). كلّ استعلام فرعيّ معزول — فشله لا يُفشِل البقيّة.
    """
    candidates: list = []
    for sql in (
        "SELECT MAX(created_at) FROM alerts",
        "SELECT MAX(created_at) FROM decision_record",
    ):
        try:
            ts = await conn.fetchval(sql)
        except Exception:  # noqa: BLE001 — مصدر غائب ⇒ يُتجاهَل
            continue
        if ts is not None:
            candidates.append(ts)
    if not candidates:
        return None
    latest = max(candidates)
    return latest.isoformat() if hasattr(latest, "isoformat") else str(latest)


@router.get("/api/v1/operations/summary")
async def operations_summary_endpoint(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """تلخيص تشغيليّ تجميعيّ للمستأجِر (RLS) — قراءة فقط. 404 إن مُطفأ، 503 إن تعذّرت القاعدة.

    يجمع عدّادات COUNT/aggregation عبر المصادر المُدامة (حقول، تنبيهات نشطة بالخطورة،
    معدّات، أجهزة، قرارات مُدامة، صمّامات/جداول ريّ) وآخر نشاط، ثمّ يُشكّلها عبر الطبقة
    النقيّة. كلّ استعلام فرعيّ best-effort: غياب مصدر ⇒ 0/None + note_ar صريح لا تلفيق.
    """
    if not _operations_wall_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة جدار مركز العمليّات غير مُفعَّلة (اضبط FEATURE_OPERATIONS_WALL).",
        )
    try:
        async with tenant_connection(user) as conn:
            counts = {
                "fields": await _scalar(conn, "SELECT COUNT(*) FROM fields"),
                "alerts_active": await _alerts_by_severity(conn),
                "equipment": await _scalar(conn, "SELECT COUNT(*) FROM equipment"),
                "iot_devices": await _scalar(conn, "SELECT COUNT(*) FROM iot_devices"),
                "decision_records": await _scalar(conn, "SELECT COUNT(*) FROM decision_record"),
                "irrigation_valves": await _scalar(conn, "SELECT COUNT(*) FROM irrigation_valves"),
                "irrigation_schedules": await _scalar(
                    conn, "SELECT COUNT(*) FROM irrigation_schedules"
                ),
                "last_activity_at": await _last_activity(conn),
            }
    except Exception as e:  # noqa: BLE001 — تعذّر فتح اتّصال المستأجِر ⇒ 503 موثَّق
        raise _db_unavailable("تلخيص العمليّات", e) from e

    out = shape_operations_summary(counts)
    out["tenant_id"] = str(user.tenant_id)  # أثر: لِمن هذا التلخيص (RLS)
    return out
