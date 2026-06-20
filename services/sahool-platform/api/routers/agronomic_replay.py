"""api/routers/agronomic_replay.py — إعادة تشغيل الموسم لحقل (قراءة فقط، #4/D)

نقطة واحدة محروسة بعلم ``FEATURE_REPLAY_MAP`` (مُطفأة افتراضاً ⇒ 404):

  • ``GET /api/v1/fields/{field_id}/agronomic-replay`` — يجمع سلاسل الحقل المُدامة
    (NDVI، ريّ، قرارات، نتائج) في **خطّ زمنيّ واحد مرتّب** لإعادة تشغيل الموسم
    (scrub)، عبر ``tenant_connection`` (عزل RLS).

**الصدق**: كلّ مسار best-effort — غياب جدوله ⇒ مسار فارغ (0) لا انهيار ولا تلفيق.
لا مصدر طقس مُدام per-field هنا ⇒ مسار الطقس فارغ صراحةً (تجلبه الواجهة من نقطته إن
لزم). 503 فقط إن تعذّر فتح اتّصال المستأجِر أصلاً.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from api.agronomic_replay import build_agronomic_replay
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}
_PER_TRACK_LIMIT = 300  # سقف لكلّ مسار (خطّ زمنيّ لا تفريغ كامل)


def _replay_map_enabled() -> bool:
    """هل ميزة إعادة تشغيل الموسم مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ)."""
    return os.getenv("FEATURE_REPLAY_MAP", "").strip().lower() in _TRUTHY


async def _rows(conn, sql: str, *args) -> list[dict]:
    """ينفّذ استعلام مسار best-effort — يعيد قائمة قواميس أو [] عند تعذّره.

    أيّ خطأ (جدول غائب/هجرة غير مطبّقة) ⇒ [] ليُعلَن المسار فارغاً (لا انهيار، لا تلفيق).
    """
    try:
        res = await conn.fetch(sql, *args)
    except Exception:  # noqa: BLE001 — مصدر غائب ⇒ مسار فارغ
        return []
    return [dict(r) for r in res]


@router.get("/api/v1/fields/{field_id}/agronomic-replay")
async def agronomic_replay_endpoint(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """خطّ زمنيّ موحّد لإعادة تشغيل موسم الحقل (RLS) — قراءة فقط. 404 إن مُطفأ، 503 إن تعذّرت القاعدة.

    يجمع NDVI/ريّ/قرارات/نتائج الحقل المُدامة (كلّ مسار best-effort) ثمّ يدمجها عبر
    الطبقة النقيّة ``build_agronomic_replay`` في أحداث مرتّبة تصاعديّاً. غياب مسار ⇒ صفر
    صريح لا تلفيق.
    """
    if not _replay_map_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة إعادة تشغيل الموسم غير مُفعَّلة (اضبط FEATURE_REPLAY_MAP).",
        )
    try:
        async with tenant_connection(user) as conn:
            ndvi = await _rows(
                conn,
                "SELECT field_id, acquisition_date, ndvi_mean FROM ndvi_timeseries "
                f"WHERE field_id = $1 ORDER BY acquisition_date DESC LIMIT {_PER_TRACK_LIMIT}",
                field_id,
            )
            irrigation = await _rows(
                conn,
                "SELECT schedule_id, name, last_run_at, water_target_mm FROM irrigation_schedules "
                f"WHERE field_id = $1 AND last_run_at IS NOT NULL ORDER BY last_run_at DESC LIMIT {_PER_TRACK_LIMIT}",
                field_id,
            )
            decisions = await _rows(
                conn,
                "SELECT decision_id, decision_type, confidence, created_at FROM decision_record "
                f"WHERE field_id = $1 ORDER BY created_at DESC LIMIT {_PER_TRACK_LIMIT}",
                field_id,
            )
            outcomes = await _rows(
                conn,
                "SELECT outcome_id, decision_id, success, created_at FROM outcome_record "
                f"WHERE field_id = $1 ORDER BY created_at DESC LIMIT {_PER_TRACK_LIMIT}",
                field_id,
            )
    except Exception as e:  # noqa: BLE001 — تعذّر فتح اتّصال المستأجِر ⇒ 503 موثَّق
        raise _db_unavailable("إعادة تشغيل الموسم", e) from e

    out = build_agronomic_replay(
        field_id,
        ndvi=ndvi,
        irrigation=irrigation,
        decisions=decisions,
        outcomes=outcomes,
        generated_at=datetime.now(UTC).isoformat(),
    )
    out["tenant_id"] = str(user.tenant_id)  # أثر: لِمن هذه الإعادة (RLS)
    return out
