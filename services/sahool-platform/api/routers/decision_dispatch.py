"""api/routers/decision_dispatch.py — موزِّع القرار المحروس (الحلقة المغلقة، P1).

# DECISION-PATH: adapter (feeds field-intelligence) — بوّابة التوزيع/التنفيذ للمسار
# القانونيّ: حواجز → تقييم (core.decision_dispatch.evaluate_dispatch) → إدراج READY.
# حارس الحَوكمة: core.decision_dispatch.assert_governance_evaluated يرفض قراراً لم
# تُقَرّ حوكمته (governance_not_evaluated) قبل التوزيع — لا تنفيذ لقرار not_evaluated.

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
import logging
import os
import uuid as _uuid
from datetime import UTC, datetime

from core.actuator_command import build_actuator_command
from core.agronomic_decision import DomainSignal, reconcile_decision, to_urgency
from core.cross_domain_optimization import optimize_irrigation
from core.decision_dispatch import evaluate_dispatch
from core.dispatch_executor import ExecutionResult, ExecutionStatus, execute_dispatch
from core.dispatch_lifecycle import assert_transition, derive_idempotency_key
from core.dispatch_notification import build_dispatch_notification, normalize_channel
from core.execution_ledger_entry import build_ledger_entry, normalize_outcome
from core.guardrails import check_guardrails
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.decision_service_client import (
    record_dispatch_decision as _mirror_dispatch_to_service,
)
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    _emit_domain_event,
    require_permission,
    tenant_connection,
)
from shared.actuation_killswitch import is_actuation_halted

router = APIRouter()
logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}


def _dispatch_enabled() -> bool:
    """هل ميزة موزِّع القرار مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ)."""
    return os.getenv("SAHOOL_DECISION_DISPATCH", "").strip().lower() in _TRUTHY


def _shape_dispatch_row(row) -> dict:
    """يحوّل صفّ dispatch_decisions إلى dict عرض — يفكّ JSONB ويُنسّق الوقت (نقيّ).

    asyncpg يعيد JSONB كنصّ خام (بلا codec) فنفكّه بـjson.loads؛ created_at →ISO.
    """

    def _loads(v):
        if v is None:
            return None
        return _json.loads(v) if isinstance(v, str) else v

    created = row["created_at"]
    return {
        "decision_id": row["decision_id"],
        "recommendation_id": row["recommendation_id"],
        "action_type": row["action_type"],
        "field_id": row["field_id"],
        "state": row["state"],
        "risk_level": row["risk_level"],
        "required_approvals": row["required_approvals"],
        "approvals_collected": row["approvals_collected"],
        "halt_breaches": _loads(row["halt_breaches"]),
        "warn_breaches": _loads(row["warn_breaches"]),
        "reason_ar": row["reason_ar"],
        "command": _loads(row["command"]),
        "exec_status": row["exec_status"],
        "created_by": row["created_by"],
        "created_at": created.isoformat() if created is not None else None,
    }


class DomainSignalIn(BaseModel):
    """إشارة مجال واحد كمدخل API — تُطبَّع إلى core.agronomic_decision.DomainSignal."""

    domain: str  # weather | soil | irrigation | pest | economics | yield
    action: str = "none"  # irrigate | spray | reduce_water | …
    urgency: str = "none"  # none|low|moderate|high|critical (مرادفات تُطبَّع)
    params: dict = {}
    halt: bool = False
    reason_ar: str = ""
    confidence: float = 1.0


class UnifiedDecisionRequest(BaseModel):
    """مدخلات المصالحة الموحّدة: حقل + إشارات المجالات المتوازية لتُجمَع في قرار واحد.

    `min_mm_for_yield` (اختياريّ): إن وُجد، تُفعَّل أمثَلة الماء متعدّدة الأهداف (الشريحة 7)
    على إجراء الريّ — توازن كفاءة الماء وأمان الغلّة وتُرفَق المفاضلة في الناتج.
    """

    field_id: str
    signals: list[DomainSignalIn]
    min_mm_for_yield: float | None = None
    water_budget_mm: float | None = None


@router.post("/api/v1/decision/unified")
def unified_decision_endpoint(
    req: UnifiedDecisionRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """مصالحة إشارات المجالات (طقس/تربة/ريّ/آفات/اقتصاد/غلّة) في قرار موحّد واحد.

    # DECISION-PATH: preview — مصالحة dry-run تُغذّي الموزِّع المحروس لاحقاً (لا تنفيذ).

    معاينة نقيّة (dry-run) — لا تنفيذ ولا كتابة قاعدة: تُجمِع التوصيات المتوازية وتُصالح
    تعارضاتها (الريّ↔الرشّ، قيد ميزانيّة الماء) بشفافيّة (reconciliations_ar). عند تمرير
    `min_mm_for_yield` تُطبَّق أمثَلة الماء متعدّدة الأهداف على إجراء الريّ (الشريحة 7).
    الخطّة الناتجة تُغذّي بعدها الموزِّع المحروس (dispatch/evaluate→execute). 404 إن مُطفأ.
    """
    if not _dispatch_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة موزِّع القرار غير مُفعَّلة (اضبط SAHOOL_DECISION_DISPATCH).",
        )
    signals = [
        DomainSignal(
            domain=s.domain,
            action=s.action or "none",
            urgency=to_urgency(s.urgency),
            params=dict(s.params),
            halt=s.halt,
            reason_ar=s.reason_ar,
            confidence=s.confidence,
        )
        for s in req.signals
    ]
    decision = reconcile_decision(req.field_id, signals)
    out = decision.to_dict()

    # أمثَلة الماء متعدّدة الأهداف (الشريحة 7) — اختياريّة، تُطبَّق على إجراء الريّ المُصالَح.
    if req.min_mm_for_yield is not None and decision.is_ready:
        for action in out["action_plan"]:
            if "irrig" in action["action"] and "water_mm" in action.get("params", {}):
                opt = optimize_irrigation(
                    float(action["params"]["water_mm"]),
                    min_mm_for_yield=req.min_mm_for_yield,
                    budget_mm=req.water_budget_mm,
                )
                action["params"]["water_mm"] = opt.applied_water_mm
                action["optimization"] = opt.to_dict()
                break

    out["reconciled_by"] = str(user.user_id)  # أثر: من طلب المصالحة
    out["dry_run"] = True  # معاينة فقط — لم يُنفَّذ شيء
    return out


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

    # مفتاح اللاتكرار يُحسَب لقرار READY فقط (هو وحده يُدرَج حيّاً في الطابور). تصليب
    # الموزِّع (v67): فهرس فريد جزئيّ يمنع إدراج أمرين حيّين لنفس التوصية ⇒ لا إطلاق مزدوج.
    idem_key = (
        derive_idempotency_key(req.recommendation_id, req.action_type, req.field_id)
        if decision.executable
        else None
    )
    decision_id = "disp_" + _uuid.uuid4().hex[:16]
    try:
        async with tenant_connection(user) as conn:
            # لاتكرار: إن وُجد قرار حيّ (queued/dispatched) بنفس المفتاح ⇒ نُعيده دون
            # إدراج جديد (إعادة نداء آمنة) — والفهرس الفريد هو الحارس النهائيّ ضدّ السباق.
            if idem_key is not None:
                existing = await conn.fetchrow(
                    "SELECT * FROM dispatch_decisions WHERE idempotency_key = $1 "
                    "AND exec_status IN ('queued', 'dispatched') ORDER BY created_at DESC LIMIT 1",
                    idem_key,
                )
                if existing is not None:
                    out = _shape_dispatch_row(existing)
                    out["replayed"] = True  # صدق: لم يُدرَج جديد — أُعيد القرار الحيّ القائم
                    out["audit"] = decision.to_audit()
                    return out

            async def _persist(dec, command_dict, exec_status):
                # ON CONFLICT DO NOTHING على الفهرس الفريد الجزئيّ — حارس قاعديّ ضدّ السباق.
                await conn.execute(
                    """INSERT INTO dispatch_decisions
                        (decision_id, tenant_id, recommendation_id, action_type, field_id,
                         state, risk_level, required_approvals, approvals_collected,
                         halt_breaches, warn_breaches, reason_ar, command, exec_status,
                         created_by, idempotency_key)
                       VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9,
                         $10::jsonb, $11::jsonb, $12, $13::jsonb, $14, $15, $16)
                       ON CONFLICT (tenant_id, idempotency_key)
                         WHERE idempotency_key IS NOT NULL
                           AND exec_status IN ('queued', 'dispatched')
                       DO NOTHING""",
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
                    (idem_key if exec_status == "queued" else None),
                )

            # مفتاح إيقاف طوارئ التشغيل (v133، fail-closed): قبل إدراج READY في الطابور.
            # مفتاح مُشتبَك (نطاق مستأجِر/حقل/صمّام) ⇒ لا يُدرَج للتنفيذ — يُدام not_executed
            # (تدقيق) بسبب واضح، والمُشغِّل لا يستهلك شيئاً. لا نُطلِق MQTT أعمى. قرار غير
            # قابل للتنفيذ (BLOCKED/PENDING) يمرّ كما هو (execute_dispatch يُسجّله not_executed).
            ks_halted = False
            ks_reason: str | None = None
            if decision.executable and command is not None:
                ks_halted, ks_reason = await is_actuation_halted(
                    conn,
                    str(user.tenant_id),
                    field_id=decision.field_id,
                    valve_id=(req.device_id or None),
                )
            if ks_halted:
                await _persist(decision, None, ExecutionStatus.NOT_EXECUTED.value)
                result = ExecutionResult(
                    status=ExecutionStatus.NOT_EXECUTED,
                    dispatch_state=decision.state.value,
                    command=None,
                    reason_ar=f"محجوب — مفتاح إيقاف الطوارئ مُشتبَك: {ks_reason}",
                )
            else:
                result = await execute_dispatch(decision, persist=_persist, command=command)
            # تدقيق (H3): حدث domain عبر outbox ضمن المعاملة — مسار غير مُعاد فقط
            # (replayed يعود مبكّراً أعلاه ولا يصل هنا). best-effort داخل _emit.
            await _emit_domain_event(
                conn,
                user,
                "DISPATCH_DECISION_RECORDED",
                "dispatch_decision",
                decision_id,
                {
                    "state": decision.state.value,
                    "action_type": decision.action_type,
                    "field_id": decision.field_id,
                    "exec_status": result.status.value,
                },
                critical=True,  # حوكمة توزيع القرار — fail-closed (لا commit بلا حدثه)
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إدامة قرار التوزيع", e) from e

    out = result.to_dict()
    out["decision_id"] = decision_id
    out["audit"] = decision.to_audit()

    # الجسر الانتقاليّ: كتابة dispatch_decisions أعلاه هي المصدر الموثوق وقد التُزِمت.
    # المِرْآة إلى decision-service best-effort — **لا ترفع أبداً** إلى مسار الطلب.
    try:
        await _mirror_dispatch_to_service(
            {
                "recommendation_id": decision.recommendation_id,
                "action_type": decision.action_type,
                "risk_level": decision.risk_level,
                "field_id": decision.field_id,
                "state": decision.state.value,
                "command": command.to_dict() if hasattr(command, "to_dict") else command,
                "created_by": str(user.user_id),
                "metadata": {
                    "decision_id": decision_id,
                    "required_approvals": decision.required_approvals,
                    "approvals_collected": decision.approvals_collected,
                    "halt_breaches": decision.halt_breaches,
                    "warn_breaches": decision.warn_breaches,
                    "reason_ar": decision.reason_ar,
                    "exec_status": result.status.value,
                },
            },
            tenant_id=str(user.tenant_id),
        )
    except Exception as e:  # noqa: BLE001 — مِرْآة best-effort: الفشل يُسجَّل ولا يُفشِل الطلب
        logger.warning(
            "decision-service mirror (dispatch %s) فشلت — كتابة المنصّة موثوقة ومحفوظة: %s",
            decision_id,
            e,
        )
    return out


@router.post("/api/v1/decision/dispatch/consume")
async def consume_dispatch_queue(
    channel: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
) -> dict:
    """يستهلك طابور القرارات المُدرَجة (queued) ويترجمها إلى إخطارات بشريّة (الشريحة 3).

    المبدأ الصريح: **نبدأ بالبشر لا بالمضخّات** — يطالب القرارات الجاهزة، يبني لكلٍّ حمولة
    إخطار (SMS/واتساب/مهمّة تطبيق) ليُنفّذها المزارع/الفنّيّ يدويّاً، ثمّ ينقل حالتها
    queued→dispatched (سُلِّمت للمستهلِك). لا أمر MQTT أعمى. الصدق: يبني الحمولة وينقل
    الحالة فقط؛ التسليم الفعليّ عبر مُسلِّم القنوات القائم/صفّ المهام طبقة لاحقة. النتيجة
    النهائيّة (نُفِّذ/فشل) تُسجَّل في السجلّ (الشريحة 4). 404 إن مُطفأ، 503 عند تعذّر القاعدة.

    FOR UPDATE SKIP LOCKED: مستهلِكان متزامنان لا يلتقطان نفس القرار (لا إخطار مزدوج).
    """
    if not _dispatch_enabled():
        raise HTTPException(
            status_code=404, detail="ميزة موزِّع القرار غير مُفعَّلة (اضبط SAHOOL_DECISION_DISPATCH)."
        )
    chan = normalize_channel(channel)
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT * FROM dispatch_decisions WHERE exec_status = 'queued' "
                "ORDER BY created_at ASC LIMIT $1 FOR UPDATE SKIP LOCKED",
                limit,
            )
            notifications = []
            for row in rows:
                target = assert_transition(row["exec_status"], "dispatched")  # fail-closed
                await conn.execute(
                    "UPDATE dispatch_decisions SET exec_status = $1 WHERE decision_id = $2",
                    target,
                    row["decision_id"],
                )
                notifications.append(build_dispatch_notification(row, chan))
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("استهلاك طابور التوزيع", e) from e
    return {
        "consumed": len(notifications),
        "channel": chan,
        "consumed_by": str(user.user_id),
        "notifications": notifications,
    }


@router.get("/api/v1/decision/dispatch/decisions")
async def list_dispatch_decisions(
    field_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """أثر تدقيق قرارات التوزيع للمستأجِر (الأحدث أوّلاً) — معزول بـRLS، خلف العلم.

    قراءة فقط. 404 إن مُطفأ، 503 عند تعذّر القاعدة. field_id اختياريّ للتصفية.
    """
    if not _dispatch_enabled():
        raise HTTPException(
            status_code=404, detail="ميزة موزِّع القرار غير مُفعَّلة (اضبط SAHOOL_DECISION_DISPATCH)."
        )
    try:
        async with tenant_connection(user) as conn:
            if field_id:
                rows = await conn.fetch(
                    "SELECT * FROM dispatch_decisions WHERE field_id = $1 "
                    "ORDER BY created_at DESC LIMIT $2",
                    field_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM dispatch_decisions ORDER BY created_at DESC LIMIT $1", limit
                )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة قرارات التوزيع", e) from e
    return {"decisions": [_shape_dispatch_row(r) for r in rows], "count": len(rows)}


@router.get("/api/v1/decision/dispatch/queue")
async def list_dispatch_queue(
    limit: int = Query(50, ge=1, le=200),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """طابور أوامر المُشغِّل المنتظِرة (exec_status=queued، الأقدم أوّلاً) للمستأجِر.

    ما ينتظر استهلاك actuator-service. قراءة فقط، معزول بـRLS، خلف العلم.
    """
    if not _dispatch_enabled():
        raise HTTPException(
            status_code=404, detail="ميزة موزِّع القرار غير مُفعَّلة (اضبط SAHOOL_DECISION_DISPATCH)."
        )
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT * FROM dispatch_decisions WHERE exec_status = 'queued' "
                "ORDER BY created_at ASC LIMIT $1",
                limit,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة طابور التوزيع", e) from e
    return {"queued": [_shape_dispatch_row(r) for r in rows], "count": len(rows)}


def _shape_ledger_row(row) -> dict:
    """يحوّل صفّ execution_ledger إلى dict عرض — يفكّ JSONB ويُنسّق الوقت (نقيّ)."""
    detail = row["detail"]
    if isinstance(detail, str):
        detail = _json.loads(detail)
    recorded = row["recorded_at"]
    return {
        "ledger_id": row["ledger_id"],
        "decision_id": row["decision_id"],
        "action_type": row["action_type"],
        "field_id": row["field_id"],
        "channel": row["channel"],
        "outcome": row["outcome"],
        "note_ar": row["note_ar"],
        "detail": detail,
        "content_hash": row["content_hash"],
        "recorded_by": row["recorded_by"],
        "recorded_at": recorded.isoformat() if recorded is not None else None,
    }


class LedgerRecordRequest(BaseModel):
    """مدخلات تسجيل نتيجة تنفيذ قرار مُسلَّم: القرار + النتيجة + سياق بشريّ."""

    decision_id: str
    outcome: str  # executed | failed (غيرها ⇒ 400)
    channel: str | None = None
    note_ar: str = ""
    detail: dict = {}


@router.post("/api/v1/decision/ledger")
async def record_execution_outcome(
    req: LedgerRecordRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
) -> dict:
    """يسجّل نتيجة تنفيذ قرار مُسلَّم (executed/failed) ويُغلِق الحلقة (الشريحة 4).

    يربط القرار بنتيجته المُقاسة في execution_ledger (append-only، content_hash للتدقيق)
    وينقل dispatch_decisions.exec_status من dispatched إلى executed/failed (محروس). الصدق:
    لا يُسجَّل إلّا لقرار في حالة dispatched (سبق تسليمه للمستهلِك) — وإلّا 409. 400 لنتيجة
    مجهولة، 404 إن غاب القرار (أو لمستأجِر آخر — RLS)، 503 عند تعذّر القاعدة. خلف العلم.
    """
    if not _dispatch_enabled():
        raise HTTPException(
            status_code=404, detail="ميزة موزِّع القرار غير مُفعَّلة (اضبط SAHOOL_DECISION_DISPATCH)."
        )
    try:
        outcome = normalize_outcome(req.outcome)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ledger_id = "led_" + _uuid.uuid4().hex[:16]
    recorded_at = datetime.now(UTC)
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM dispatch_decisions WHERE decision_id = $1 FOR UPDATE",
                req.decision_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="القرار غير موجود (أو لمستأجِر آخر).")
            try:
                target = assert_transition(row["exec_status"], outcome)  # dispatched→outcome
            except ValueError as e:
                raise HTTPException(
                    status_code=409,
                    detail=f"لا يُسجَّل تنفيذ لقرار في حالة {row['exec_status']!r}: {e}",
                ) from e

            entry = build_ledger_entry(
                row,
                outcome=target,
                recorded_at=recorded_at.isoformat(),
                channel=req.channel,
                note_ar=req.note_ar,
                detail=req.detail,
            )
            await conn.execute(
                """INSERT INTO execution_ledger
                    (ledger_id, tenant_id, decision_id, action_type, field_id, channel,
                     outcome, note_ar, detail, content_hash, recorded_by, recorded_at)
                   VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12)""",
                ledger_id,
                str(user.tenant_id),
                entry["decision_id"],
                entry["action_type"],
                entry["field_id"],
                entry["channel"],
                entry["outcome"],
                entry["note_ar"],
                _json.dumps(entry["detail"]),
                entry["content_hash"],
                str(user.user_id),
                recorded_at,
            )
            await conn.execute(
                "UPDATE dispatch_decisions SET exec_status = $1 WHERE decision_id = $2",
                target,
                req.decision_id,
            )
            # تدقيق (H3): حدث domain عبر outbox ضمن المعاملة (best-effort داخل _emit).
            await _emit_domain_event(
                conn,
                user,
                "DISPATCH_EXECUTION_RECORDED",
                "dispatch_decision",
                req.decision_id,
                {
                    "outcome": target,
                    "decision_id": req.decision_id,
                    "field_id": entry["field_id"],
                },
                critical=True,  # تنفيذ القرار — fail-closed (لا commit بلا حدثه)
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تسجيل نتيجة التنفيذ", e) from e

    out = dict(entry)
    out["ledger_id"] = ledger_id
    out["recorded_by"] = str(user.user_id)
    return out


@router.get("/api/v1/decision/ledger")
async def list_execution_ledger(
    field_id: str | None = None,
    decision_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """سجلّ التنفيذ للمستأجِر (الأحدث أوّلاً) — معزول بـRLS، خلف العلم.

    قراءة فقط. تصفية اختياريّة بـfield_id/decision_id. 404 إن مُطفأ، 503 عند تعذّر القاعدة.
    """
    if not _dispatch_enabled():
        raise HTTPException(
            status_code=404, detail="ميزة موزِّع القرار غير مُفعَّلة (اضبط SAHOOL_DECISION_DISPATCH)."
        )
    clauses, args = [], []
    if field_id:
        args.append(field_id)
        clauses.append(f"field_id = ${len(args)}")
    if decision_id:
        args.append(decision_id)
        clauses.append(f"decision_id = ${len(args)}")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    args.append(limit)
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                f"SELECT * FROM execution_ledger{where} "
                f"ORDER BY recorded_at DESC LIMIT ${len(args)}",
                *args,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سجلّ التنفيذ", e) from e
    return {"ledger": [_shape_ledger_row(r) for r in rows], "count": len(rows)}
