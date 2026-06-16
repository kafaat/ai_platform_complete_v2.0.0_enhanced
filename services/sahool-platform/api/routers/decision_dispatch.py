"""api/routers/decision_dispatch.py — موزِّع القرار المحروس (الحلقة المغلقة، P1).

يُسطِّح دماغ الموزِّع (`core.decision_dispatch`) عبر نقطتين، محروستين بعلم
`SAHOOL_DECISION_DISPATCH` (مُطفأ افتراضاً ⇒ 404؛ إنضاج تدريجيّ):

  • `POST …/dispatch/evaluate` — **معاينة (dry-run)**: حواجز → تقييم → قرار + أثر
    تدقيق. لا تنفيذ، لا كتابة قاعدة. «ماذا سيقرّر الموزِّع؟».
  • `POST …/dispatch/execute` — **تنفيذ محروس**: حواجز → تقييم → إدامة في
    `dispatch_decisions` (تدقيق) + إدراج **READY فقط** (`exec_status=queued`)
    ليستهلكه actuator-service. BLOCKED/PENDING يُسجَّل ولا يُنفَّذ.

**أمان**: التنفيذ الفيزيائيّ (نشر MQTT الموقَّع) يبقى في actuator-service المُحصَّن؛
هذه النقطة **تُدرِج** الأمر فقط (طابور)، لا تُطلِق MQTT أعمى. الحاجز (guardrails) +
بوّابة الموافقة (طبقات human_in_loop) مُنفَّذان بنيويّاً: لا يُدرَج إلّا قرار مُخلَّص.
ربط بوّابة الموافقة الحيّة + استهلاك المُشغِّل للطابور + تسجيل التكلفة في ERPNext
الافتراضيّ/farm_ledger: خطوات تشغيليّة تالية — انظر docs/ARCHITECTURE_DEPENDENCY_AND_GAPS_2026-06.
"""

from __future__ import annotations

import json as _json
import os
import uuid as _uuid

from core.actuator_command import build_actuator_command
from core.decision_dispatch import evaluate_dispatch
from core.dispatch_executor import execute_dispatch
from core.guardrails import check_guardrails
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

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


class DispatchExecuteRequest(DispatchEvaluateRequest):
    """مدخلات تنفيذ القرار: نفس مدخلات المعاينة + هدف التنفيذ (جهاز/أمر/معاملات).

    device_id/command إلزاميّان فعليّاً **فقط عند READY** (قرار مُخلَّص) — وإلّا
    لا يُبنى أمر أصلاً (يُسجَّل not_executed). لذا اختياريّان هنا.
    """

    device_id: str | None = None
    command: str | None = None
    params: dict = {}


@router.post("/api/v1/decision/dispatch/execute")
async def execute_dispatch_endpoint(
    req: DispatchExecuteRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
) -> dict:
    """ينفّذ قرار توزيع محروساً: حواجز → تقييم → إدامة (تدقيق) + إدراج READY فقط.

    404 إن كانت الميزة مُطفأة. BLOCKED/PENDING ⇒ يُسجَّل بـnot_executed ولا يُنفَّذ.
    READY ⇒ يُبنى أمر المُشغِّل ويُدرَج (exec_status=queued) ليستهلكه actuator-service —
    لا إطلاق MQTT من هنا. 422 إن غاب device_id/command لقرار READY. 503 عند تعذّر القاعدة.
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

    # أمر المُشغِّل يُبنى لقرار READY فقط (fail-closed داخل build_actuator_command).
    command = None
    if decision.executable:
        try:
            command = build_actuator_command(
                decision,
                device_id=req.device_id or "",
                command=req.command or "",
                params=req.params,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    decision_id = "disp_" + _uuid.uuid4().hex[:16]
    try:
        async with tenant_connection(user) as conn:

            async def _persist(dec, command_dict, exec_status):
                await conn.execute(
                    """INSERT INTO dispatch_decisions
                        (decision_id, tenant_id, recommendation_id, action_type, field_id,
                         state, risk_level, required_approvals, approvals_collected,
                         halt_breaches, warn_breaches, reason_ar, command, exec_status, created_by)
                       VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9,
                         $10::jsonb, $11::jsonb, $12, $13::jsonb, $14, $15)""",
                    decision_id,
                    str(user.tenant_id),
                    dec.recommendation_id,
                    dec.action_type,
                    dec.field_id,
                    dec.state.value,
                    dec.risk_level,
                    dec.required_approvals,
                    dec.approvals_collected,
                    _json.dumps(dec.halt_breaches),
                    _json.dumps(dec.warn_breaches),
                    dec.reason_ar,
                    (_json.dumps(command_dict) if command_dict is not None else None),
                    exec_status,
                    str(user.user_id),
                )

            result = await execute_dispatch(decision, persist=_persist, command=command)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إدامة قرار التوزيع", e) from e

    out = result.to_dict()
    out["decision_id"] = decision_id
    out["audit"] = decision.to_audit()
    return out
