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

from collections.abc import Callable
from typing import Any

from core.workflow_engine import (
    InMemoryWorkflowStore,
    WorkflowStep,
    run_workflow,
)


def build_pest_escalation_steps(
    *,
    detect_fn: Callable[[dict], dict] | None = None,
    execute_fn: Callable[[dict], dict] | None = None,
    cancel_fn: Callable[[dict], Any] | None = None,
) -> list[WorkflowStep]:
    """يبني خطوات تصعيد الآفة. الدوال الخارجيّة (رصد/تنفيذ) قابلة للحقن.

    detect_fn(ctx) → {pest_type, severity}؛ execute_fn(ctx) → {executed};
    cancel_fn(ctx) تعويض تنفيذ فاشل. بلا حقن تُستخدم منطق افتراضي من السياق.
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
        # تأكيد الخطورة عبر عتبات alert_engine (صدق: لا تأكيد بلا شدّة كافية)
        sev = float(ctx.get("severity", 0.0))
        if sev >= 0.7:
            level = CRITICAL
        elif sev >= 0.4:
            level = WARNING
        else:
            level = "info"
        confirmed = sev >= 0.4  # دون ذلك: لا تصعيد (تجنّب إنذار كاذب)
        return {"alert_level": level, "confirmed": confirmed}

    def step_recommend(ctx: dict) -> dict:
        # توصية الإجراء بحسب الخطورة (صدق: لا توصية إن لم يُؤكَّد)
        if not ctx.get("confirmed"):
            return {"recommendation_ar": "لا تصعيد — الشدّة دون عتبة التدخّل", "action_type": "none"}
        sev = float(ctx.get("severity", 0.0))
        if sev >= 0.7:
            return {
                "recommendation_ar": "مكافحة عاجلة — رشّ موجّه + عزل البؤرة",
                "action_type": "urgent_spray",
            }
        return {
            "recommendation_ar": "مراقبة مكثّفة + مكافحة حيويّة وقائيّة",
            "action_type": "biocontrol",
        }

    def step_await_approval(ctx: dict) -> dict:
        # تعليق للموافقة البشريّة — قرار حقلي يحتاج خبيراً (إلّا لو لا تصعيد)
        return {"approval_requested": bool(ctx.get("confirmed")), "approval_status": "pending"}

    def step_execute(ctx: dict) -> dict:
        # تنفيذ بعد الموافقة (له تعويض Saga). صدق: لا تنفيذ بلا موافقة/إجراء
        if ctx.get("action_type") in (None, "none"):
            return {"executed": False, "note_ar": "لا إجراء للتنفيذ"}
        if execute_fn is not None:
            res = execute_fn(ctx)
            return {
                "executed": bool(res.get("executed", True)),
                "execution_ref": res.get("execution_ref"),
            }
        return {"executed": True, "execution_ref": f"exec-{ctx.get('action_type')}"}

    def undo_execute(ctx: dict) -> None:
        # تعويض Saga: إلغاء التنفيذ إن فشلت خطوة لاحقة (المتابعة)
        if cancel_fn is not None and ctx.get("execution_ref"):
            cancel_fn(ctx)

    def step_follow_up(ctx: dict) -> dict:
        # جدولة متابعة للتحقّق من نجاح المكافحة
        if not ctx.get("executed"):
            return {"follow_up_scheduled": False}
        return {
            "follow_up_scheduled": True,
            "follow_up_note_ar": "متابعة بعد 7 أيّام للتحقّق من تراجع الإصابة",
        }

    return [
        WorkflowStep("detect", step_detect),
        WorkflowStep("confirm", step_confirm),
        WorkflowStep("recommend", step_recommend),
        WorkflowStep("await_approval", step_await_approval, suspends=True),
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
