"""تدفّق تصعيد الآفة — أوّل استخدام فعلي لـworkflow_engine في قرار زراعي.

يحوّل workflow_engine من بنية مُختبَرة معزولة إلى تدفّق قرار حيّ. يربط:
- alert_engine (تصنيف خطورة الآفة)
- workflow_engine (durability + استئناف + تعليق للموافقة + Saga)
- correlation (خيط تتبّع موحّد عبر الخطوات)
- human-in-the-loop (الموافقة البشريّة عبر suspends — قرارات حقليّة تحتاج خبيراً)

المراحل (LangGraph/Temporal pattern):
  ① detect    — رصد الآفة (شدّة + نوع)
  ② confirm   — تأكيد عبر تصنيف الخطورة (alert_engine)
  ③ recommend — توصية الإجراء (رشّ/مكافحة حيويّة)
  ④ approve   — تعليق للموافقة البشريّة (suspends — خبير يراجع)
  ⑤ execute   — تنفيذ بعد الموافقة (له تعويض Saga: إلغاء الجدولة)
  ⑥ follow_up — جدولة متابعة للتحقّق من النتيجة

الخطوات نقيّة-بايثون قابلة للحقن (fns)؛ التنفيذ الفعلي (نداء خدمات) يُمرَّر
عبر action_fns ليبقى التدفّق مُختبَراً دون تبعيّات حيّة. صدق: التعذّر يُعلَن،
الخطوة الفاشلة توقف التدفّق قابلاً للاستئناف.
"""

from __future__ import annotations

import logging
import math
import os
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from core.workflow_engine import (
    InMemoryWorkflowStore,
    WorkflowStatus,
    WorkflowStep,
    run_workflow,
)

logger = logging.getLogger(__name__)

# ── جدول التصعيد التصريحي (declarative escalation table) ──
# العتبات والمصفوفة (شدّة → مستوى/إجراء) معرَّفة هنا بدل تشتّتها داخل المنطق
# كأرقام سحريّة — تماماً كنمط alert_engine (عتبات مُسمّاة قابلة للمعايرة). صدق:
# القيم مطابقة للسلوك السابق حرفيّاً؛ هذا تنظيم لا تغيير سلوك.

# عتبات الشدّة (قابلة للمعايرة بحقول الجوف)
_SEVERITY_CRITICAL = 0.7  # عندها فأعلى: خطورة حرجة + مكافحة عاجلة
_SEVERITY_INTERVENTION = 0.4  # عتبة التدخّل: دونها لا تصعيد (تجنّب إنذار كاذب)

# مصفوفة الإجراء حسب نطاق الشدّة (شدّة مؤكَّدة فقط). تُقرأ بالترتيب: أوّل نطاق
# تتجاوز الشدّةُ حدَّه الأدنى يَحكم. كلّ صفّ تصريحيّ: (الحدّ الأدنى, الإجراء, التوصية).
_ACTION_BANDS: tuple[tuple[float, str, str], ...] = (
    (_SEVERITY_CRITICAL, "urgent_spray", "مكافحة عاجلة — رشّ موجّه + عزل البؤرة"),
    (_SEVERITY_INTERVENTION, "biocontrol", "مراقبة مكثّفة + مكافحة حيويّة وقائيّة"),
)

# توصية «لا تصعيد» (دون عتبة التدخّل أو غير مؤكَّد)
_NO_ESCALATION_ACTION = "none"
_NO_ESCALATION_RECOMMENDATION = "لا تصعيد — الشدّة دون عتبة التدخّل"

# ملاحظة الحجب حين لا يحمل حكم السلامة سبباً
_GATE_BLOCKED_NOTE = "لا يُنفَّذ: لم يسمح فحص السلامة الكيميائيّة بالتنفيذ"

# حالات الموافقة التي تسمح بالتنفيذ / لا تتطلّب تعليقاً (HIL)
_APPROVAL_CLEARED = frozenset({"approved", "not_required"})

# عرض للقراءة فقط للجدول التصريحي (للاختبار/التفتيش دون كسر الثبات)
ESCALATION_TABLE = MappingProxyType(
    {
        "severity_critical": _SEVERITY_CRITICAL,
        "severity_intervention": _SEVERITY_INTERVENTION,
        "action_bands": _ACTION_BANDS,
        "approval_cleared": _APPROVAL_CLEARED,
    }
)


# ── إثبات التنفيذ (PEST-EXECUTE-DEFAULT-ACK-01) ──
# executed=True لا يُعلَن إلّا بإقرار صريح من المنفّذ: ``executed is True`` مع مرجع تنفيذ.
EXECUTOR_NOT_CONFIGURED = "executor_not_configured"
EXECUTION_NOT_CONFIRMED = "execution_not_confirmed"
EXECUTION_REF_MISSING = "execution_ref_missing"
_EXECUTOR_NOT_CONFIGURED_NOTE = "لم يُنفَّذ: لا منفّذ موصول لهذا الإجراء — القرار يبقى بشريّاً"
_EXECUTION_NOT_CONFIRMED_NOTE = "لم يُنفَّذ: المنفّذ لم يؤكّد التنفيذ صراحةً"
_EXECUTION_REF_MISSING_NOTE = "لم يُعدّ منفّذاً: أعلن المنفّذ التنفيذ بلا مرجع تنفيذ"


def _execution_ref(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def is_execution_proven(result: Mapping[str, Any] | None) -> bool:
    """تنفيذ مُثبَت: ``executed is True`` مع ``execution_ref`` نصّيّ غير فارغ."""
    return (
        isinstance(result, Mapping)
        and result.get("executed") is True
        and _execution_ref(result.get("execution_ref")) is not None
    )


def summarize_pest_execution(state: Any) -> dict[str, Any]:
    """Project physical pest execution without trusting workflow completion.

    A completed workflow can have no executor. Conversely, a crash during
    execution or an unacknowledged worker reply can have already caused a
    physical effect. The latter must be reconciled, never called "no spray".
    The projection is read-only and does not modify the durable workflow.
    """
    step = state.step_results.get("execute")
    if not isinstance(step, Mapping):
        # A failed/in-flight execute step has no receipt precisely because
        # its handler can crash AFTER the side effect and BEFORE saving the
        # result. current_step is saved before invoking the handler.
        reached_execute = (
            state.current_step in ("execute", "follow_up")
            or "execute" in state.completed_steps
        )
        uncertain = (
            reached_execute
            or state.status in (WorkflowStatus.COMPLETED, WorkflowStatus.COMPENSATION_FAILED)
        )
        return {
            "status": "reconciliation_required" if uncertain else "not_attempted",
            "executed": None if uncertain else False,
            "execution_ref": None,
            "reason": "execution_outcome_unknown" if uncertain else "execution_step_not_reached",
        }

    ref = _execution_ref(step.get("execution_ref"))
    proven = is_execution_proven(step)
    ack = step.get("executed")
    # Both failure reason codes are emitted AFTER the executor was called.
    # A false-shaped reply from a called executor does not prove no side effect.
    uncertain = (
        state.status == WorkflowStatus.COMPENSATION_FAILED
        or (ref is not None and not proven)
        or (not proven and ack is not False)
        or step.get("reason") in (EXECUTION_NOT_CONFIRMED, EXECUTION_REF_MISSING)
        or (proven and state.status != WorkflowStatus.COMPLETED)
    )
    status = "reconciliation_required" if uncertain else "executed" if proven else "not_executed"
    reason = step.get("reason") or step.get("blocked_by")
    if not isinstance(reason, str) or not reason.strip():
        reason = (
            "execution_reconciliation_required"
            if uncertain
            else None
            if proven
            else "execution_not_confirmed"
        )
    return {
        "status": status,
        "executed": None if uncertain else proven,
        "execution_ref": ref,
        "reason": reason,
    }


def _execution_outcome(res: object) -> dict:
    """يحوّل ردّ execute_fn إلى نتيجة صادقة. لا نجاح بلا إقرار صريح ومرجع."""
    body = res if isinstance(res, Mapping) else {}
    ref = _execution_ref(body.get("execution_ref"))
    if body.get("executed") is True and ref is not None:
        return {"executed": True, "execution_ref": ref}
    if body.get("executed") is True:
        return {
            "executed": False,
            "execution_ref": None,
            "reason": EXECUTION_REF_MISSING,
            "note_ar": _EXECUTION_REF_MISSING_NOTE,
        }
    # المرجع يُحفَظ إن وُجد ليتمكّن تعويض Saga من إلغاء أثرٍ جزئيّ.
    return {
        "executed": False,
        "execution_ref": ref,
        "reason": EXECUTION_NOT_CONFIRMED,
        "note_ar": _EXECUTION_NOT_CONFIRMED_NOTE,
    }


def build_pest_escalation_steps(
    *,
    detect_fn: Callable[[dict], dict] | None = None,
    execute_fn: Callable[[dict], dict] | None = None,
    cancel_fn: Callable[[dict], Any] | None = None,
    safety_gate_fn: Callable[[dict], dict] | None = None,
) -> list[WorkflowStep]:
    """يبني خطوات تصعيد الآفة. الدوال الخارجيّة (رصد/تنفيذ) قابلة للحقن.

    detect_fn(ctx) → {pest_type, severity}؛ execute_fn(ctx) → {executed, execution_ref};
    cancel_fn(ctx) تعويض تنفيذ فاشل. بلا حقن تُستخدم منطق افتراضي من السياق.

    التنفيذ مُثبَت فقط حين يعيد execute_fn ``executed is True`` حرفيّاً مع
    ``execution_ref`` نصّيّ غير فارغ. غير ذلك (حقل غائب، {}، مرجع غائب) ⇒ executed=False
    مع سبب. بلا execute_fn ⇒ executed=False وسبب ``executor_not_configured``.

    safety_gate_fn(ctx) → حكم السلامة الكيميائيّة (guardrails-engine من الخادم، W0-01).
    التنفيذ لا يحدث إلّا إذا أعاد ``{"allowed": True, ...}`` حرفيّاً. غيابه أو رفضه أو
    خطؤه ⇒ لا تنفيذ (fail-closed): موافقة الخبير وحدها لا تكفي لرشّ مبيد.
    """
    from core.alert_engine import CRITICAL, WARNING

    def step_detect(ctx: dict) -> dict:
        # رصد الآفة — من detect_fn (نموذج/حسّاس) أو من السياق المُمرَّر
        if detect_fn is not None:
            res = detect_fn(ctx)
        else:
            res = {
                "pest_type": ctx.get("pest_type", "غير محدّد"),
                "severity": ctx.get("severity", 0.0),
            }
        return {"pest_type": res.get("pest_type"), "severity": float(res.get("severity", 0.0))}

    def step_confirm(ctx: dict) -> dict:
        # تأكيد الخطورة عبر عتبات alert_engine (صدق: لا تأكيد بلا شدّة كافية).
        # العتبات من الجدول التصريحي أعلاه (لا أرقام سحريّة في المنطق).
        sev = float(ctx.get("severity", 0.0))
        if sev >= _SEVERITY_CRITICAL:
            level = CRITICAL
        elif sev >= _SEVERITY_INTERVENTION:
            level = WARNING
        else:
            level = "info"
        confirmed = sev >= _SEVERITY_INTERVENTION  # دون ذلك: لا تصعيد (تجنّب إنذار كاذب)
        return {"alert_level": level, "confirmed": confirmed}

    def step_recommend(ctx: dict) -> dict:
        # توصية الإجراء بحسب الخطورة (صدق: لا توصية إن لم يُؤكَّد). المصفوفة
        # تصريحيّة (_ACTION_BANDS): أوّل نطاق تتجاوز الشدّةُ حدَّه الأدنى يَحكم.
        if not ctx.get("confirmed"):
            return {
                "recommendation_ar": _NO_ESCALATION_RECOMMENDATION,
                "action_type": _NO_ESCALATION_ACTION,
            }
        sev = float(ctx.get("severity", 0.0))
        for threshold, action_type, recommendation_ar in _ACTION_BANDS:
            if sev >= threshold:
                return {"recommendation_ar": recommendation_ar, "action_type": action_type}
        # احتياط: شدّة مؤكَّدة لكن دون أدنى نطاق (لا يقع عمليّاً — التأكيد ≥ عتبة التدخّل)
        return {
            "recommendation_ar": _NO_ESCALATION_RECOMMENDATION,
            "action_type": _NO_ESCALATION_ACTION,
        }

    def step_await_approval(ctx: dict) -> dict:
        # لا تصعيد مؤكّد ⇒ لا حاجة لموافقة (لا نُعلّق بلا داعٍ).
        if not ctx.get("confirmed"):
            return {"approval_requested": False, "approval_status": "not_required"}
        # موافقة الخبير تصل عبر initial_context عند الاستئناف (approval_status=approved).
        # قبلها تبقى pending ⇒ يتوقّف الـworkflow (التعليق المشروط أدناه).
        return {
            "approval_requested": True,
            "approval_status": ctx.get("approval_status", "pending"),
        }

    def _needs_approval_suspend(ctx: dict) -> bool:
        # تعليق مشروط: نُعلّق فقط حين تكون الموافقة فعلاً معلّقة (pending). مسار
        # «لا تصعيد» (not_required) أو الموافقة المعتمَدة (approved) لا يُعلّق ⇒
        # لا حاجة لطلب استئناف بلا معنى للحالات التي لا تنتظر خبيراً.
        return ctx.get("approval_status") not in _APPROVAL_CLEARED

    def _evaluate_safety_gate(ctx: dict) -> dict:
        # fail-closed: لا بوّابة ⇒ حجب؛ استثناء أو حكم ليس dict ⇒ حجب.
        if safety_gate_fn is None:
            return {
                "allowed": False,
                "status": "gate_not_configured",
                "reason_ar": "لا يُنفَّذ: بوّابة السلامة الكيميائيّة غير موصولة.",
            }
        try:
            verdict = safety_gate_fn(ctx)
        except Exception as exc:  # noqa: BLE001 — مسار سلامة: الخطأ حجب
            return {
                "allowed": False,
                "status": "error",
                "reason_ar": _GATE_BLOCKED_NOTE,
                "error": type(exc).__name__,
            }
        if not isinstance(verdict, dict):
            return {"allowed": False, "status": "error", "reason_ar": _GATE_BLOCKED_NOTE}
        return dict(verdict)

    def step_execute(ctx: dict) -> dict:
        # HIL فعليّ: لا تنفيذ إلّا بموافقة معتمَدة (أو لا حاجة لها). كان ينفّذ رغم
        # بقاء الموافقة "pending" ⇒ كان الـHIL شكليّاً.
        if ctx.get("approval_status") not in _APPROVAL_CLEARED:
            return {"executed": False, "note_ar": "بانتظار موافقة الخبير — لم يُنفَّذ"}
        if ctx.get("action_type") in (None, _NO_ESCALATION_ACTION):
            return {"executed": False, "note_ar": "لا إجراء للتنفيذ"}
        # بوّابة السلامة الكيميائيّة (W0-01): بعد موافقة الخبير وقبل أيّ أثر جانبيّ.
        verdict = _evaluate_safety_gate(ctx)
        if verdict.get("allowed") is not True:
            return {
                "executed": False,
                "blocked_by": "guardrails",
                "guardrails": verdict,
                "note_ar": verdict.get("reason_ar") or _GATE_BLOCKED_NOTE,
            }
        if execute_fn is None:
            # PEST-EXECUTE-DEFAULT-ACK-01: no executor wired ⇒ nothing ran. This branch used
            # to answer executed=True with a made-up ref "exec-<action_type>", which scheduled
            # a 7-day follow-up for a spray that never happened.
            return {
                "executed": False,
                "execution_ref": None,
                "reason": EXECUTOR_NOT_CONFIGURED,
                "note_ar": _EXECUTOR_NOT_CONFIGURED_NOTE,
                "guardrails": verdict,
            }
        res = execute_fn(ctx)
        return {**_execution_outcome(res), "guardrails": verdict}

    def undo_execute(ctx: dict) -> None:
        # تعويض Saga: إلغاء التنفيذ إن فشلت خطوة لاحقة (المتابعة)
        if cancel_fn is not None and ctx.get("execution_ref"):
            cancel_fn(ctx)

    def step_follow_up(ctx: dict) -> dict:
        # جدولة متابعة للتحقّق من نجاح المكافحة — لتنفيذ مُثبَت فقط (executed is True
        # مع مرجع تنفيذ غير فارغ). قيمة truthy أو مرجع غائب لا تُجدوِل متابعة لما لم يقع.
        if not is_execution_proven(ctx):
            return {"follow_up_scheduled": False}
        return {
            "follow_up_scheduled": True,
            "follow_up_note_ar": "متابعة بعد 7 أيّام للتحقّق من تراجع الإصابة",
        }

    return [
        WorkflowStep("detect", step_detect),
        WorkflowStep("confirm", step_confirm),
        WorkflowStep("recommend", step_recommend),
        WorkflowStep("await_approval", step_await_approval, suspends=_needs_approval_suspend),
        WorkflowStep("execute", step_execute, compensate=undo_execute),
        WorkflowStep("follow_up", step_follow_up),
    ]


def run_pest_escalation(
    workflow_id: str,
    *,
    store: Any = None,
    tenant_id: str | None = None,
    initial_context: dict | None = None,
    detect_fn: Callable | None = None,
    execute_fn: Callable | None = None,
    cancel_fn: Callable | None = None,
    safety_gate_fn: Callable | None = None,
    compensate_on_failure: bool = True,
):
    """يشغّل/يستأنف تدفّق تصعيد الآفة. مرحلة الموافقة تُعلّق الـworkflow.

    أوّل تشغيل: يصل لـawait_approval ثمّ يُعلَّق (suspended). بعد موافقة الخبير،
    استدعاء ثانٍ بنفس workflow_id يُستأنف من execute → follow_up.
    التنفيذ يتطلّب أيضاً ``safety_gate_fn`` يسمح صراحةً (انظر build_pest_escalation_steps).
    """
    steps = build_pest_escalation_steps(
        detect_fn=detect_fn,
        execute_fn=execute_fn,
        cancel_fn=cancel_fn,
        safety_gate_fn=safety_gate_fn,
    )
    return run_workflow(
        workflow_id,
        steps,
        store=store if store is not None else InMemoryWorkflowStore(),
        tenant_id=tenant_id,
        initial_context=initial_context,
        compensate_on_failure=compensate_on_failure,
    )


# ══ بوّابة السلامة الكيميائيّة (guardrails-engine من الخادم، W0-01) ══
#
# كانت الواجهة تستدعي ``/api/guardrails/v1/validate`` من المتصفّح. ذلك المسار يقبل توكن
# خدمة فقط فيردّ 401، والواجهة كانت تعامل الخطأ «قرار الخبير» فتعيد تفعيل الموافقة على
# المبيد بلا أيّ فحص كيميائيّ (airuntime-1 / web-2). هنا يُبنى ``GuardrailsRequest``
# للمبيد على الخادم ويُرسَل بتوكن الخدمة، وخطوة التنفيذ في تدفّق الآفة لا تنفّذ إلّا إذا
# أعاد المحرّك ``allowed is True`` حرفيّاً.
#
# fail-closed مطلق: أيّ نتيجة غير ``allowed is True`` حجبٌ — رفض، أو 401/403، أو 422
# (عقد الأدلّة)، أو مهلة، أو خطأ شبكة، أو JSON غير صالح، أو توكن خدمة غائب، أو أدلّة ناقصة.
#
# الأدلّة: عقد guardrails للمبيد يطلب المادّة والجرعة والتكلفة والعائد المتوقّع وسياق
# المزرعة الاقتصاديّ. تدفّق الآفة اليوم لا يحمل أيّاً منها، والعميل لا يستطيع حقنها (الموجِّه
# ينسخ حقولاً محدّدة فقط إلى السياق). فحتى يصل منشئ سياق الحوكمة (W1-12) يكون الطلب
# ``evidence_unavailable`` ولا يُرسَل أصلاً، والتنفيذ محجوب ويبقى القرار بيد البشر خارج النظام.
# الفحص المحلّيّ للأدلّة تقليلٌ لنداء محكوم بالرفض فقط، لا بديل عن عقد المحرّك: لو انحرف
# العقد فالمحرّك يردّ 422 وهو حجب أيضاً.

# نوع إجراء guardrails لكلّ إجراء ينفّذه تدفّق الآفة. المكافحة الحيويّة قد تستعمل مبيداً
# حيويّاً، والمنصّة لا تملك ما يفصلها عن الكيميائيّ، فتُحكَم كمبيد (fail-closed).
GUARDRAILS_ACTION_TYPE = "pesticide"

# أدلّة عقد guardrails للمبيد (services/guardrails-engine/contracts.py). المصدر القانونيّ
# هو المحرّك؛ هذه نسخة للحجب المبكّر برسالة صادقة فقط.
ACTION_EVIDENCE_KEYS: tuple[str, ...] = (
    "chemical",
    "dosage_kg_ha",
    "cost_usd",
    "projected_revenue_increase_usd",
)
FARM_EVIDENCE_KEYS: tuple[str, ...] = (
    "annual_revenue_usd",
    "annual_costs_usd",
    "cash_reserve_usd",
)

# Declared limitation (W1-12 review): these keys have no server source today, so the gate
# cannot reach ``allowed`` and every execute step blocks (fail closed). The treatment (product,
# dose, cost, expected benefit) is not read from any server record (the flow context carries
# none, and the request body is not trusted), and no table records a farm's cash reserve.
# Filling them needs an owner decision on the source of record; the verdict names them so a
# block for a missing source is not read as missing data the farmer could still enter.
NO_SERVER_SOURCE_EVIDENCE: tuple[str, ...] = (
    *(f"action_data.{k}" for k in ACTION_EVIDENCE_KEYS),
    "farm_context.cash_reserve_usd",
)

# حالات الحكم. ``allowed`` وحدها تسمح بالتنفيذ.
ALLOWED = "allowed"
DENIED = "denied"
EVIDENCE_UNAVAILABLE = "evidence_unavailable"
IDENTITY_UNAVAILABLE = "identity_unavailable"
SERVICE_TOKEN_MISSING = "service_token_missing"
UNAUTHORIZED = "unauthorized"
CONTRACT_REJECTED = "contract_rejected"
TIMEOUT = "timeout"
UNREACHABLE = "unreachable"
ERROR = "error"

_DEFAULT_URL = "http://sahool-guardrails-engine:8000"
_DEFAULT_TIMEOUT_S = 10.0


def _verdict(status: str, reason_ar: str, **extra: Any) -> dict:
    return {
        "allowed": status == ALLOWED,
        "status": status,
        "reason_ar": reason_ar,
        "source": "guardrails-engine:/v1/validate",
        **extra,
    }


def is_execution_allowed(verdict: object) -> bool:
    """هل يسمح الحكم بالتنفيذ؟ فقط ``allowed is True`` في dict. أيّ شيء آخر حجب."""
    return isinstance(verdict, Mapping) and verdict.get("allowed") is True


def _present(value: object) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    return False


def _guardrails_user_id(user_id: object) -> int | None:
    """``GuardrailsRequest.user_id`` عدد موجب (users.id). غير ذلك ⇒ None (حجب)."""
    if isinstance(user_id, bool):
        return None
    if isinstance(user_id, int):
        return user_id if 0 < user_id <= 2147483647 else None
    text = str(user_id or "").strip()
    if text.isascii() and text.isdecimal():
        value = int(text)
        return value if 0 < value <= 2147483647 else None
    return None


def build_pesticide_guardrails_request(
    ctx: Mapping[str, Any],
    *,
    tenant_id: str,
    user_id: object,
    farm_context: Mapping[str, Any] | None = None,
) -> tuple[dict | None, list[str]]:
    """يبني حمولة ``GuardrailsRequest`` للمبيد من سياق التدفّق وحقائق الخادم.

    يُرجِع (الحمولة، الحقول الناقصة). الحمولة None حين تنقص أدلّة أو هويّة.
    ``farm_context`` يأتي من الخادم (منشئ W1-12) لا من جسم الطلب.
    """
    farm = dict(farm_context or {})
    missing = [f"action_data.{k}" for k in ACTION_EVIDENCE_KEYS if not _present(ctx.get(k))]
    missing += [f"farm_context.{k}" for k in FARM_EVIDENCE_KEYS if not _present(farm.get(k))]
    gr_user = _guardrails_user_id(user_id)
    if gr_user is None:
        missing.append("user_id")
    if missing:
        return None, missing

    action_data: dict = {k: ctx.get(k) for k in ACTION_EVIDENCE_KEYS}
    for key in ("action_type", "pest_type", "severity", "recommendation_ar"):
        if ctx.get(key) is not None:
            action_data["intervention" if key == "action_type" else key] = ctx.get(key)
    if ctx.get("field_id"):
        farm.setdefault("field_id", ctx.get("field_id"))
    if ctx.get("season_id"):
        farm.setdefault("season_id", ctx.get("season_id"))
    payload = {
        "action_type": GUARDRAILS_ACTION_TYPE,
        "action_data": action_data,
        "farm_context": farm,
        "user_id": gr_user,
        "tenant_id": str(tenant_id),
        "request_source": "user",
        # موافقة الخبير حصلت في التدفّق؛ الحكم هنا للسلامة لا لتخطّي المراجعة.
        "auto_approve_low_risk": True,
    }
    return payload, []


def evaluate_pesticide_guardrails(
    ctx: Mapping[str, Any],
    *,
    tenant_id: str,
    user_id: object,
    farm_context_fn: Callable[[str, str | None], Mapping[str, Any] | None] | None = None,
    transport: Any = None,
) -> dict:
    """يحكم على تنفيذ مبيد عبر guardrails-engine. لا يرفع أبداً؛ كلّ تعذّر حجب.

    ``farm_context_fn(tenant_id, field_id)`` نقطة حقن لمنشئ سياق الحوكمة (W1-12)؛
    غيابه ⇒ لا حقائق اقتصاديّة ⇒ ``evidence_unavailable``. ``transport`` للاختبار فقط.
    """
    try:
        farm: Mapping[str, Any] | None = None
        if farm_context_fn is not None:
            farm = farm_context_fn(str(tenant_id), ctx.get("field_id"))
        payload, missing = build_pesticide_guardrails_request(
            ctx, tenant_id=tenant_id, user_id=user_id, farm_context=farm
        )
        if payload is None:
            status = IDENTITY_UNAVAILABLE if missing == ["user_id"] else EVIDENCE_UNAVAILABLE
            return _verdict(
                status,
                "لا يُنفَّذ المبيد: أدلّة فحص السلامة الكيميائيّة غير متاحة على الخادم "
                f"({'، '.join(missing)}). القرار يبقى بشريّاً خارج النظام.",
                missing_fields=missing,
                no_server_source=[k for k in missing if k in NO_SERVER_SOURCE_EVIDENCE],
            )

        token = os.getenv("SAHOOL_AGENT_TOKEN", "").strip()
        if not token:
            return _verdict(
                SERVICE_TOKEN_MISSING,
                "لا يُنفَّذ المبيد: توكن الخدمة غير مضبوط، فتعذّر فحص السلامة الكيميائيّة.",
            )

        import httpx

        url = os.getenv("GUARDRAILS_URL", _DEFAULT_URL).rstrip("/") + "/v1/validate"
        try:
            timeout_s = float(os.getenv("GUARDRAILS_TIMEOUT_S", str(_DEFAULT_TIMEOUT_S)))
        except ValueError:
            timeout_s = _DEFAULT_TIMEOUT_S
        client_kwargs: dict = {"timeout": timeout_s}
        if transport is not None:
            client_kwargs["transport"] = transport
        try:
            with httpx.Client(**client_kwargs) as client:
                resp = client.post(url, json=payload, headers={"X-Agent-Token": token})
        except httpx.TimeoutException:
            return _verdict(TIMEOUT, "لا يُنفَّذ المبيد: انتهت مهلة فحص السلامة الكيميائيّة.")
        except httpx.HTTPError as exc:
            return _verdict(
                UNREACHABLE,
                "لا يُنفَّذ المبيد: تعذّر الوصول لمحرّك السلامة الكيميائيّة.",
                error=type(exc).__name__,
            )

        if resp.status_code in (401, 403):
            return _verdict(
                UNAUTHORIZED,
                "لا يُنفَّذ المبيد: محرّك السلامة رفض هويّة الخدمة.",
                http_status=resp.status_code,
            )
        if resp.status_code == 422:
            return _verdict(
                CONTRACT_REJECTED,
                "لا يُنفَّذ المبيد: محرّك السلامة رفض الطلب لنقص الأدلّة أو عدم صلاحيّتها.",
                http_status=422,
            )
        if resp.status_code != 200:
            return _verdict(
                ERROR,
                "لا يُنفَّذ المبيد: محرّك السلامة أعاد خطأً.",
                http_status=resp.status_code,
            )
        try:
            body = resp.json()
        except ValueError:
            return _verdict(ERROR, "لا يُنفَّذ المبيد: ردّ محرّك السلامة غير صالح.")
        if not isinstance(body, dict):
            return _verdict(ERROR, "لا يُنفَّذ المبيد: ردّ محرّك السلامة غير صالح.")

        details = {
            "overall_risk": body.get("overall_risk"),
            "requires_human_approval": body.get("requires_human_approval"),
            "approval_workflow_id": body.get("approval_workflow_id"),
            "arabic_explanation": body.get("arabic_explanation"),
        }
        if body.get("allowed") is True and body.get("evaluation_only") is not True:
            return _verdict(ALLOWED, "سمح محرّك السلامة الكيميائيّة بالتنفيذ.", **details)
        return _verdict(
            DENIED,
            body.get("arabic_explanation") or "لا يُنفَّذ المبيد: لم يسمح محرّك السلامة.",
            **details,
        )
    except Exception as exc:  # noqa: BLE001 — مسار سلامة: أيّ خطأ حجب، لا رفع
        logger.warning("pesticide guardrails gate failed closed: %s", type(exc).__name__)
        return _verdict(
            ERROR,
            "لا يُنفَّذ المبيد: خطأ في فحص السلامة الكيميائيّة.",
            error=type(exc).__name__,
        )
