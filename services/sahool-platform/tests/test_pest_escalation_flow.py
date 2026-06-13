"""اختبارات تدفّق تصعيد الآفة (HIL) — بوّابة الموافقة قبل الرشّ (سلامة).

فجوة تغطية حرجة (مراجعة الجولة ٣): تدفّق يقود قرار **رشّ مبيد** خلف موافقة خبير
(suspend). كان بلا اختبار ⇒ خطر تنفيذ رشّ بلا موافقة. هنا نقفل: شدّة عالية تُعلّق
(لا رشّ)، الاستئناف بعد الموافقة يُنفّذ، والشدّة المنخفضة لا تُصعّد ولا تَرشّ.
"""

from core.pest_escalation_flow import run_pest_escalation
from core.workflow_engine import InMemoryWorkflowStore, WorkflowStatus


def test_high_severity_suspends_for_approval_no_spray_yet():
    store = InMemoryWorkflowStore()
    sprayed: list[int] = []
    st = run_pest_escalation(
        "pe1",
        store=store,
        initial_context={"pest_type": "locust", "severity": 0.9},
        execute_fn=lambda ctx: sprayed.append(1) or {"executed": True, "execution_ref": "x"},
    )
    assert st.status == WorkflowStatus.SUSPENDED  # معلّق بانتظار الخبير
    assert sprayed == []  # لم يُرشَّ بلا موافقة (HIL فعليّ لا شكليّ)


def test_resume_after_approval_executes_spray_once():
    store = InMemoryWorkflowStore()
    sprayed: list[int] = []

    def _exec(ctx):
        sprayed.append(1)
        return {"executed": True, "execution_ref": "x"}

    run_pest_escalation(
        "pe2",
        store=store,
        initial_context={"pest_type": "locust", "severity": 0.9},
        execute_fn=_exec,
    )
    assert sprayed == []  # قبل الموافقة: لا رشّ
    # موافقة الخبير تصل عبر الاستئناف بنفس workflow_id + المتجر.
    st = run_pest_escalation(
        "pe2",
        store=store,
        initial_context={"approval_status": "approved"},
        execute_fn=_exec,
    )
    assert st.status == WorkflowStatus.COMPLETED
    assert sprayed == [1]  # رُشَّ بعد الموافقة، مرّة واحدة فقط


def test_low_severity_no_escalation_no_spray():
    store = InMemoryWorkflowStore()
    sprayed: list[int] = []
    st = run_pest_escalation(
        "pe3",
        store=store,
        initial_context={"pest_type": "aphid", "severity": 0.2},
        execute_fn=lambda ctx: sprayed.append(1) or {"executed": True},
    )
    assert st.status == WorkflowStatus.COMPLETED  # لا تعليق (دون عتبة التدخّل)
    assert sprayed == []  # لا رشّ لشدّة منخفضة
