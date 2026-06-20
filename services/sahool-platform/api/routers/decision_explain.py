"""api/routers/decision_explain.py — نقطة شرح/إعادة تشغيل القرار (Explainable + Replay)

تُغلق رأس «لماذا هذا القرار، وماذا حدث فعلاً؟»: القرار الكامل مُدام (decision_record v78،
decision_value JSONB) ونتائجه (outcome_record v79)، لكنّ شرحه يبقى متناثراً في حقول
decision_value وأثره الميدانيّ في جدول آخر. هذه النقطة تجمعهما في عرض واحد:

  • `GET /api/v1/decision/{decision_id}/explain` — تقرأ decision_record (معزولة بـRLS) +
    نتائجه المربوطة، وتُرجِع **سلسلة شرح مُهيكَلة** (عبر الطبقة النقيّة explain_decision):
    ثقة → إشارات (حالة المدخلات) → سياسة → قيود → إجراء، + النتائج (replay: ماذا حدث
    فعلاً) + ملخّص دليل المنطقة إن توفّر (evidence_from_persisted_outcomes).

محروسة بعلم `FEATURE_DECISION_STUDIO` (مُطفأ افتراضاً ⇒ 404؛ نمط الإغلاق المرن
كـdecision_dispatch — إنضاج تدريجيّ). قراءة فقط لا كتابة قاعدة.

النمط محفوظ (كـdecision_record/learning_summary): قراءة async عبر tenant_connection
(معزولة بـRLS)، 503 عبر _db_unavailable، require_permission(RECOMMENDATION_VIEW).
الصدق: الشرح نقيّ (explain_decision) — الحقل الغائب ⇒ غياب صريح لا اختلاق؛ النتائج
حقيقيّة من القاعدة (replay)؛ calibrated=false. مسار القراءة تكامليّ (يتطلّب Postgres،
مُختبَر كـdecision_dispatch لا وحدويّاً)؛ منطق الشرح مُختبَر وحدويّاً بلا قاعدة.
"""

from __future__ import annotations

import json as _json
import os

from fastapi import APIRouter, Depends, HTTPException, Query

from api.decision_explain import explain_decision
from api.evidence_registry import evidence_from_persisted_outcomes
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.routers.decision_record import _shape_decision_row, _shape_outcome_row

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}


def _decision_studio_enabled() -> bool:
    """هل ميزة استوديو القرار (شرح/إعادة) مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ، إغلاق مرن)."""
    return os.getenv("FEATURE_DECISION_STUDIO", "").strip().lower() in _TRUTHY


def _evidence_summary(region: str | None, orows: list) -> dict | None:
    """ملخّص دليل المنطقة من نتائج القرار المُدامة إن توفّرت منطقة — None إن غابت (لا اختلاق).

    يفوّض إلى evidence_from_persisted_outcomes (مصدر واحد لعتبة field_verified). الصفوف
    تُمرَّر بـmetrics مفكوكة (JSONB ⇒ dict) وcreated_at كما هو — منطق العتبة نقيّ هناك.
    """
    if not region or not orows:
        return None
    rows = [{"metrics": r["metrics"], "created_at": r["created_at"]} for r in orows]
    return evidence_from_persisted_outcomes(region, rows)


@router.get("/api/v1/decision/{decision_id}/explain")
async def explain_decision_endpoint(
    decision_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """يشرح قراراً مُداماً (سلسلة مُهيكَلة) ويُعيد نتائجه (replay) + ملخّص الدليل — قراءة فقط.

    يقرأ decision_record + outcome_record المربوطة (معزولة بـRLS)، يستخرج سلسلة الشرح عبر
    الطبقة النقيّة explain_decision (ثقة/إشارات/سياسة/قيود/إجراء — الغائب يُكشَف لا يُختلق)،
    ويُرفِق النتائج الفعليّة (replay) وملخّص دليل المنطقة. القرار المفقود (لم يُدَم/لمستأجِر
    آخر) ⇒ 404. 404 إن كان العلم مُطفأ (إغلاق مرن، قبل لمس القاعدة). 503 عند تعذّر القاعدة.
    """
    if not _decision_studio_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة استوديو القرار غير مُفعَّلة (اضبط FEATURE_DECISION_STUDIO).",
        )
    try:
        async with tenant_connection(user) as conn:
            drow = await conn.fetchrow(
                "SELECT * FROM decision_record WHERE decision_id = $1", decision_id
            )
            orows = await conn.fetch(
                "SELECT * FROM outcome_record WHERE decision_id = $1 "
                "ORDER BY created_at ASC LIMIT $2",
                decision_id,
                limit,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة شرح القرار", e) from e

    # القرار المفقود ⇒ 404 (لا شرح لقرار غير مُدام/لمستأجِر آخر — RLS).
    if drow is None:
        raise HTTPException(status_code=404, detail="القرار غير موجود (أو لم يُدَم/لمستأجِر آخر).")

    decision = _shape_decision_row(drow)
    decision_value = decision["decision_value"]
    if isinstance(decision_value, str):  # حارس: JSONB قد يعود نصّاً خاماً
        decision_value = _json.loads(decision_value)

    explanation = explain_decision(decision_value)  # سلسلة الشرح المُهيكَلة (نقيّ)
    outcomes = [_shape_outcome_row(r) for r in orows]  # replay: ماذا حدث فعلاً
    evidence = _evidence_summary(decision["region"], orows)  # ملخّص دليل المنطقة (أو None)

    return {
        "decision_id": decision_id,
        "decision_type": decision["decision_type"],
        "field_id": decision["field_id"],
        "region": decision["region"],
        "confidence": decision["confidence"],
        "created_at": decision["created_at"],
        "explanation": explanation,
        "outcomes": outcomes,  # النتائج المُدامة (replay)
        "outcome_count": len(outcomes),
        "evidence": evidence,  # ملخّص دليل المنطقة إن توفّر (None لا اختلاق)
        "calibrated": False,  # السلسلة مشتقّة من قرار غير معايَر — تُعلَن لا تُخفى
    }
