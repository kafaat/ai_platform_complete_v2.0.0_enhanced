"""api/routers/execution_feedback.py — رصد حلقة التنفيذ (قراءة فقط، P1)

نقطة واحدة محروسة بعلم ``FEATURE_EXECUTION_FEEDBACK`` (مُطفأة افتراضاً ⇒ 404):

  • ``GET /api/v1/execution/feedback`` — لكلّ قرار مُدام حديث للمستأجِر: هل **نُفِّذ**
    (من ``execution_ledger``)؟ وهل **طابقت النتيجةُ الخطّةَ** (من ``outcome_record``)؟
    عبر ``tenant_connection`` (عزل RLS)، فيُغلق حلقة Decision→Execution→Outcome.

**رصد قراءة فقط**: لا يُصدِر أمراً ولا يُعيد تنفيذاً — يقرأ السجلّات المُدامة فقط. كلّ
ضمّ best-effort (جدول غائب ⇒ يُعامَل غياب القيد honestly). 503 إن تعذّرت القاعدة كليّاً.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from api.execution_feedback import shape_execution_feedback
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}
_MAX_DECISIONS = 200


def _execution_feedback_enabled() -> bool:
    """هل ميزة رصد حلقة التنفيذ مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ)."""
    return os.getenv("FEATURE_EXECUTION_FEEDBACK", "").strip().lower() in _TRUTHY


async def _rows(conn, sql: str, *args) -> list[dict]:
    """ينفّذ استعلام best-effort — [] عند تعذّره (جدول غائب ⇒ يُعامَل غياب القيد)."""
    try:
        res = await conn.fetch(sql, *args)
    except Exception:  # noqa: BLE001 — مصدر غائب ⇒ لا قيود (تُعلَن unknown/unmeasured)
        return []
    return [dict(r) for r in res]


@router.get("/api/v1/execution/feedback")
async def execution_feedback_endpoint(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """رصد حلقة تنفيذ قرارات المستأجِر (RLS) — قراءة فقط. 404 إن مُطفأ، 503 إن تعذّرت القاعدة.

    يضمّ أحدث قرارات ``decision_record`` بأحدث قيد ``execution_ledger`` وأحدث
    ``outcome_record`` لكلّ قرار، ثمّ يُشكّل عبر الطبقة النقيّة (حالة الحلقة لكلّ قرار +
    ملخّص). صدق: لا قيد تنفيذ ⇒ unknown، لا نتيجة ⇒ unmeasured (لا افتراض). لا تنفيذ هنا.
    """
    if not _execution_feedback_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة رصد حلقة التنفيذ غير مُفعَّلة (اضبط FEATURE_EXECUTION_FEEDBACK).",
        )
    try:
        async with tenant_connection(user) as conn:
            decisions = await _rows(
                conn,
                "SELECT decision_id, decision_type, field_id, created_at FROM decision_record "
                f"ORDER BY created_at DESC LIMIT {_MAX_DECISIONS}",
            )
            ledger = await _rows(
                conn,
                "SELECT DISTINCT ON (decision_id) decision_id, outcome, recorded_at, note_ar "
                "FROM execution_ledger ORDER BY decision_id, recorded_at DESC",
            )
            outcomes = await _rows(
                conn,
                "SELECT DISTINCT ON (decision_id) decision_id, success "
                "FROM outcome_record ORDER BY decision_id, created_at DESC",
            )
    except Exception as e:  # noqa: BLE001 — تعذّر فتح اتّصال المستأجِر ⇒ 503 موثَّق
        raise _db_unavailable("رصد حلقة التنفيذ", e) from e

    ledger_by = {str(r["decision_id"]): r for r in ledger}
    outcome_by = {str(r["decision_id"]): r for r in outcomes}

    rows: list[dict] = []
    for d in decisions:
        did = str(d["decision_id"])
        lg = ledger_by.get(did)
        oc = outcome_by.get(did)
        created = d.get("created_at")
        rec_at = lg.get("recorded_at") if lg else None
        rows.append(
            {
                "decision_id": did,
                "decision_type": d.get("decision_type"),
                "field_id": d.get("field_id"),
                "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
                "execution_outcome": lg.get("outcome") if lg else None,
                "executed_at": rec_at.isoformat() if hasattr(rec_at, "isoformat") else rec_at,
                "exec_note_ar": lg.get("note_ar") if lg else None,
                "has_outcome": oc is not None,
                "outcome_success": oc.get("success") if oc else None,
            }
        )

    out = shape_execution_feedback(rows, generated_at=datetime.now(UTC).isoformat())
    out["tenant_id"] = str(user.tenant_id)  # أثر: لِمن هذا الرصد (RLS)
    return out
