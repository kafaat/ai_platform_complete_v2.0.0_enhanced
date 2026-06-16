"""api/routers/decision_dispatch.py — معاينة قرار التوزيع المحروس (dry-run، قراءة فقط).

الشريحة ٢ من P1 (الحلقة المغلقة): تُسطِّح دماغ الموزِّع (`core.decision_dispatch`)
كنقطة **معاينة آمنة** — تأخذ توصيةً + سياق حواجز، تُشغّل `core.guardrails.check_guardrails`
ثمّ `evaluate_dispatch`، وتُرجِع القرار + أثر التدقيق. **لا تُنفّذ شيئاً** (لا أمر مُشغِّل،
لا كتابة قاعدة) — معاينة فقط: «ماذا سيقرّر الموزِّع المحروس لهذه التوصية؟».

محروسة بعلم `SAHOOL_DECISION_DISPATCH` (مُطفأ افتراضاً ⇒ 404): الميزة قيد الإنضاج،
لا تُعرَض حتى تُفعَّل صراحةً. التنفيذ الفعليّ (إصدار أمر المُشغِّل عبر guardrails-engine
+ بوّابة موافقة + تسجيل التكلفة في ERPNext/farm_ledger) شريحة لاحقة تستهلك
`state == READY` فقط — انظر docs/ARCHITECTURE_DEPENDENCY_AND_GAPS_2026-06.
"""

from __future__ import annotations

import os

from core.decision_dispatch import evaluate_dispatch
from core.guardrails import check_guardrails
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.main import Permission, UserSchema, require_permission

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}


def _dispatch_enabled() -> bool:
    """هل ميزة موزِّع القرار مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ)."""
    return os.getenv("SAHOOL_DECISION_DISPATCH", "").strip().lower() in _TRUTHY


class DispatchEvaluateRequest(BaseModel):
    """مدخلات معاينة قرار التوزيع: التوصية + سياق الحواجز (كلّه اختياريّ بحدود آمنة)."""

    recommendation_id: str
    action_type: str
    risk_level: str  # LOW | MEDIUM | HIGH | CRITICAL (مجهول ⇒ يُعامَل CRITICAL)
    field_id: str | None = None
    approvals_collected: int = 0
    # سياق الحواجز (يُمرَّر إلى check_guardrails كما هو):
    pesticide_phi_satisfied: bool | None = None
    has_governing_data: bool = True
    soil_ec_ds_m: float | None = None
    crop_salinity_threshold_ds_m: float | None = None
    deficit_salinity_risk: str | None = None
    zone_factor_calibrated: bool = False


@router.post("/api/v1/decision/dispatch/evaluate")
def evaluate_dispatch_endpoint(
    req: DispatchEvaluateRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """معاينة (dry-run) لقرار التوزيع المحروس — لا تنفيذ. 404 إن كانت الميزة مُطفأة.

    تُشغّل الحواجز ثمّ الموزِّع وتُرجِع أثر التدقيق (state: blocked|pending_approval|ready،
    الخروق، الموافقات المطلوبة، السبب). الشريحة اللاحقة هي مَن يُنفّذ READY فعليّاً.
    """
    if not _dispatch_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة موزِّع القرار غير مُفعَّلة (اضبط SAHOOL_DECISION_DISPATCH).",
        )
    guardrail = check_guardrails(
        pesticide_phi_satisfied=req.pesticide_phi_satisfied,
        has_governing_data=req.has_governing_data,
        soil_ec_ds_m=req.soil_ec_ds_m,
        crop_salinity_threshold_ds_m=req.crop_salinity_threshold_ds_m,
        deficit_salinity_risk=req.deficit_salinity_risk,
        zone_factor_calibrated=req.zone_factor_calibrated,
    )
    decision = evaluate_dispatch(
        recommendation_id=req.recommendation_id,
        action_type=req.action_type,
        risk_level=req.risk_level,
        guardrail=guardrail,
        field_id=req.field_id,
        approvals_collected=req.approvals_collected,
    )
    audit = decision.to_audit()
    audit["evaluated_by"] = str(user.user_id)  # من عاين (أثر)
    audit["dry_run"] = True  # معاينة فقط — لم يُنفَّذ شيء
    return audit
