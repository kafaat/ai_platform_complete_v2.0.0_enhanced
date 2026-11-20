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

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from core.workflow_engine import (
    InMemoryWorkflowStore,
    WorkflowState,
    WorkflowStatus,
    WorkflowStep,
    run_workflow,
)

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


_LEGACY_EXECUTION_REFS = frozenset(f"exec-{action}" for _, action, _ in _ACTION_BANDS)


def _execution_ref(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    return None


def is_execution_proven(result: Mapping[str, Any] | None) -> bool:
    """تنفيذ مُثبَت: ``executed is True`` مع ``execution_ref`` نصّيّ غير فارغ."""
    return (
        isinstance(result, Mapping)
        and result.get("executed") is True
        and (ref := _execution_ref(result.get("execution_ref"))) is not None
        and ref not in _LEGACY_EXECUTION_REFS
    )


def summarize_pest_execution(state: WorkflowState) -> dict[str, Any]:
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
            state.current_step in ("execute", "follow_up") or "execute" in state.completed_steps
        )
        uncertain = reached_execute or state.status in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.COMPENSATION_FAILED,
        )
        return {
            "status": "reconciliation_required" if uncertain else "not_attempted",
            "executed": None if uncertain else False,
            "execution_ref": None,
            "reason": "execution_outcome_unknown" if uncertain else "execution_step_not_reached",
        }

    ref = _execution_ref(step.get("execution_ref"))
    # The legacy no-executor fallback emitted the same reference for every
    # workflow with this action. It cannot identify a physical operation.
    if ref in _LEGACY_EXECUTION_REFS:
        return {
            "status": "reconciliation_required",
            "executed": None,
            "execution_ref": None,
            "reason": "legacy_synthetic_reference",
        }
    proven = is_execution_proven(step)
    ack = step.get("executed")
    # Both failure reason codes are emitted AFTER the executor was called.
    # A false-shaped reply from a called executor does not prove no side effect.
    uncertain = (
        state.status == WorkflowStatus.COMPENSATION_FAILED
        or (ref is not None and not proven)
        or (not proven and ack is not False)
        or step.get("reason") in ("execution_not_confirmed", "execution_ref_missing")
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


def build_pest_escalation_steps(
    *,
    detect_fn: Callable[[dict], dict] | None = None,
    execute_fn: Callable[[dict], dict] | None = None,
    cancel_fn: Callable[[dict], Any] | None = None,
) -> list[WorkflowStep]:
    """يبني خطوات تصعيد الآفة. الدوال الخارجيّة (رصد/تنفيذ) قابلة للحقن.

    detect_fn(ctx) → {pest_type, severity}؛ execute_fn(ctx) → {executed, execution_ref};
    cancel_fn(ctx) تعويض فشل. بلا منفذ فعليّ لا يوجد إقرار تنفيذ.
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

    def step_execute(ctx: dict) -> dict:
        # HIL فعليّ: لا تنفيذ إلّا بموافقة معتمَدة (أو لا حاجة لها). كان ينفّذ رغم
        # بقاء الموافقة "pending" ⇒ كان الـHIL شكليّاً.
        if ctx.get("approval_status") not in _APPROVAL_CLEARED:
            return {"executed": False, "note_ar": "بانتظار موافقة الخبير — لم يُنفَّذ"}
        if ctx.get("action_type") in (None, _NO_ESCALATION_ACTION):
            return {"executed": False, "note_ar": "لا إجراء للتنفيذ"}
        if execute_fn is None:
            # A workflow has no physical actuator unless the caller wires a real one.
            return {
                "executed": False,
                "execution_ref": None,
                "reason": "executor_not_configured",
            }
        res = execute_fn(ctx)
        if is_execution_proven(res):
            return {"executed": True, "execution_ref": _execution_ref(res["execution_ref"])}
        # An attempted side effect may be uncertain, but never count it as executed
        # without a literal positive ACK and nonblank reference.
        return {
            "executed": False,
            "execution_ref": None,
            "reason": "execution_not_confirmed",
        }

    def undo_execute(ctx: dict) -> None:
        # تعويض Saga: إلغاء التنفيذ إن فشلت خطوة لاحقة (المتابعة)
        if cancel_fn is not None and ctx.get("execution_ref"):
            cancel_fn(ctx)

    def step_follow_up(ctx: dict) -> dict:
        # جدولة متابعة للتحقّق من نجاح المكافحة
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
    compensate_on_failure: bool = True,
):
    """يشغّل/يستأنف تدفّق تصعيد الآفة. مرحلة الموافقة تُعلّق الـworkflow.

    أوّل تشغيل: يصل لـawait_approval ثمّ يُعلَّق (suspended). بعد موافقة الخبير،
    استدعاء ثانٍ بنفس workflow_id يُستأنف من execute → follow_up.
    """
    steps = build_pest_escalation_steps(
        detect_fn=detect_fn, execute_fn=execute_fn, cancel_fn=cancel_fn
    )
    return run_workflow(
        workflow_id,
        steps,
        store=store if store is not None else InMemoryWorkflowStore(),
        tenant_id=tenant_id,
        initial_context=initial_context,
        compensate_on_failure=compensate_on_failure,
    )
