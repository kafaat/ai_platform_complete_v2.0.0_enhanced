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

from api.learning_summary import summarize_learning_with_reconciled_outcomes
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
                "SELECT outcome_id, field_id, region, decision_id, success, metrics, "
                "planned, actual, stage, created_at FROM outcome_record"
            )
            # Optional v49/v66 bridge: these tables may be absent in partial deployments.
            # Absence must not hide outcome_record evidence or turn the dashboard into 503.
            rorows = []
            dispatch_rows = []
            try:
                rorows = await conn.fetch(
                    "SELECT outcome_id, field_id, season_id, crop, recommendation_id, "
                    "predicted_yield_t_ha, actual_yield_t_ha, accepted, matured_within_lag, "
                    "issued_at, outcome_recorded_at FROM recommendation_outcomes"
                )
            except Exception:  # noqa: BLE001 — optional bridge table; absence ⇒ zero yield-learning rows
                rorows = []
            try:
                dispatch_rows = await conn.fetch(
                    "SELECT recommendation_id, decision_id FROM dispatch_decisions"
                )
            except Exception:  # noqa: BLE001 — optional link table; absence ⇒ no soft linking
                dispatch_rows = []
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة حلقة التعلّم", e) from e

    # تطبيع الصفوف لمدخلات التجميع النقيّ (metrics JSONB ⇒ dict؛ created_at كما هو).
    decision_rows = [{"region": r["region"], "created_at": r["created_at"]} for r in drows]
    outcome_rows = [
        {
            "outcome_id": r["outcome_id"],
            "field_id": r["field_id"],
            "region": r["region"],
            "decision_id": r["decision_id"],
            "success": r["success"],
            "metrics": _loads(r["metrics"]) or {},
            "planned": _loads(r["planned"]),
            "actual": _loads(r["actual"]),
            "stage": r["stage"],
            "created_at": r["created_at"],
        }
        for r in orows
    ]
    recommendation_outcomes = [
        {
            "outcome_id": r["outcome_id"],
            "field_id": r["field_id"],
            "season_id": r["season_id"],
            "crop": r["crop"],
            "recommendation_id": r["recommendation_id"],
            "predicted_yield_t_ha": r["predicted_yield_t_ha"],
            "actual_yield_t_ha": r["actual_yield_t_ha"],
            "accepted": r["accepted"],
            "matured_within_lag": r["matured_within_lag"],
            "issued_at": r["issued_at"],
            "outcome_recorded_at": r["outcome_recorded_at"],
        }
        for r in rorows
    ]
    dispatch_links = {
        r["recommendation_id"]: r["decision_id"]
        for r in dispatch_rows
        if r["recommendation_id"] and r["decision_id"]
    }

    summary = summarize_learning_with_reconciled_outcomes(
        decision_rows,
        outcome_rows,
        recommendation_outcomes,
        dispatch_links=dispatch_links,
    )
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
