"""api/routers/learning_summary.py — نقطة تلخيص حلقة التعلّم (Learning Dashboard data)

تُغلق رأس عرض حلقة التعلّم: لوحة الرصد تحتاج لقطةً مُجمَّعة لحالة الحلقة المُدامة
(Decision→Outcome→Evidence) لكلّ منطقة — وهي قراءة فقط فوق جداول قائمة (decision_record
v78، outcome_record v79). محروسة بعلم `FEATURE_LEARNING_DASHBOARD` (مُطفأ افتراضاً ⇒ 404؛
نمط الإغلاق المرن كـdecision_dispatch — إنضاج تدريجيّ).

  • `GET /api/v1/learning/summary` — لكلّ منطقة (+ إجماليّ): عدد القرارات المُدامة، عدد
    النتائج، نسبة النجاح (من outcome_record.success)، مستوى الدليل/عدّ العيّنات نحو
    field_verified (عبر evidence_from_persisted_outcomes)، آخر نشاط.

النمط محفوظ (كـdecision_record/decision_dispatch): قراءة async عبر tenant_connection
(معزولة بـRLS)، 503 عبر _db_unavailable، require_permission(RECOMMENDATION_VIEW).
الصدق: التجميع نقيّ (summarize_learning) — counts/success_rate حقيقيّة من القاعدة؛ الناقص
⇒ None/0 لا تلفيق؛ calibrated=false للعتبات التقديريّة. مسار القراءة تكامليّ (يتطلّب
Postgres، مُختبَر كـdecision_dispatch لا وحدويّاً)؛ منطق التجميع مُختبَر وحدويّاً بلا قاعدة.
"""

from __future__ import annotations

import json as _json
import os

from fastapi import APIRouter, Depends, HTTPException

from api.learning_summary import summarize_learning
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}


def _learning_dashboard_enabled() -> bool:
    """هل لوحة رصد حلقة التعلّم مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ، إغلاق مرن)."""
    return os.getenv("FEATURE_LEARNING_DASHBOARD", "").strip().lower() in _TRUTHY


def _loads(v):
    """asyncpg يعيد JSONB كنصّ خام (بلا codec) ⇒ نفكّه؛ None/dict يمرّان كما هما."""
    if v is None:
        return None
    return _json.loads(v) if isinstance(v, str) else v


@router.get("/api/v1/learning/summary")
async def get_learning_summary(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """يُجمِّع حالة حلقة التعلّم المُدامة للوحة الرصد — قراءة فقط، معزول بـRLS.

    لكلّ منطقة (+ إجماليّ): عدد القرارات/النتائج، نسبة النجاح من outcome_record.success،
    مستوى الدليل/العيّنات نحو field_verified، آخر نشاط. 404 إن كان العلم مُطفأ (إغلاق مرن).
    503 عند تعذّر القاعدة. التجميع نقيّ (summarize_learning)؛ counts حقيقيّة، الناقص ⇒ None/0.
    """
    if not _learning_dashboard_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة لوحة حلقة التعلّم غير مُفعَّلة (اضبط FEATURE_LEARNING_DASHBOARD).",
        )
    try:
        async with tenant_connection(user) as conn:
            drows = await conn.fetch("SELECT region, created_at FROM decision_record")
            orows = await conn.fetch(
                "SELECT region, success, metrics, created_at FROM outcome_record"
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة حلقة التعلّم", e) from e

    # تطبيع الصفوف لمدخلات التجميع النقيّ (metrics JSONB ⇒ dict؛ created_at كما هو).
    decision_rows = [{"region": r["region"], "created_at": r["created_at"]} for r in drows]
    outcome_rows = [
        {
            "region": r["region"],
            "success": r["success"],
            "metrics": _loads(r["metrics"]) or {},
            "created_at": r["created_at"],
        }
        for r in orows
    ]

    summary = summarize_learning(decision_rows, outcome_rows)
    # تنسيق الطوابع الزمنيّة (datetime ⇒ ISO) في اللقطة المُجمَّعة — التجميع نفسه يبقى نقيّاً.
    _isoformat_stamps(summary)
    return summary


_STAMP_KEYS = ("last_decision_at", "last_outcome_at", "last_activity_at")


def _isoformat_stamps(summary: dict) -> None:
    """ينسّق طوابع كلّ منطقة + الإجماليّ إلى ISO (datetime ⇒ str) في المكان — لا منطق تجميع.

    التجميع النقيّ (summarize_learning) يمرّر created_at كما وَرَد (datetime من asyncpg)؛
    نُنسّقه هنا في طبقة الموجِّه (حدود I/O) لإبقاء منطق التجميع حتميّاً بلا اعتماد نوعٍ زمنيّ.
    """

    def _iso(snap: dict) -> None:
        for k in _STAMP_KEYS:
            v = snap.get(k)
            if v is not None and hasattr(v, "isoformat"):
                snap[k] = v.isoformat()

    for region_snap in summary.get("regions", []):
        _iso(region_snap)
    if summary.get("overall"):
        _iso(summary["overall"])
