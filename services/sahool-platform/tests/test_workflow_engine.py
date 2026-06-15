"""اختبارات محرّك الـworkflow (Saga) — استئناف idempotent، تعليق، تعويض.

فجوة تغطية حرجة (مراجعة الجولة ٣): المحرّك يقود قرارات ذات أثر جانبيّ (دفع/رشّ) عبر
استئناف + تعويض Saga، وكان بلا اختبار. هنا نقفل: لا إعادة تنفيذ لخطوة أثر جانبيّ عند
الاستئناف، التعليق يوقف ويُستأنف، والفشل يُعوَّض عكسيّاً.
"""

from core.workflow_engine import (
    InMemoryWorkflowStore,
    WorkflowStatus,
    WorkflowStep,
    run_workflow,
)


def test_resume_does_not_replay_completed_side_effecting_step():
    store = InMemoryWorkflowStore()
    calls = {"s1": 0}

    def s1(ctx):
        calls["s1"] += 1  # أثر جانبيّ (مثلاً دفعة/إرسال)
        return {"a": 1}

    def s2_fail(ctx):
        raise RuntimeError("boom")

    steps = [WorkflowStep("s1", s1), WorkflowStep("s2", s2_fail)]
    st1 = run_workflow("wf1", steps, store=store)
    assert st1.status == WorkflowStatus.FAILED
    assert calls["s1"] == 1
    # الاستئناف لا يُعيد تنفيذ s1 (المكتملة) — يبدأ من s2 الفاشلة.
    st2 = run_workflow("wf1", steps, store=store)
    assert calls["s1"] == 1  # لم يُعَد الأثر الجانبيّ
    assert st2.status == WorkflowStatus.FAILED


def test_suspend_halts_then_resumes_without_replay():
    store = InMemoryWorkflowStore()
    ran: list[str] = []

    steps = [
        WorkflowStep("s1", lambda ctx: ran.append("s1") or {}, suspends=True),
        WorkflowStep("s2", lambda ctx: ran.append("s2") or {}),
    ]
    st = run_workflow("wf2", steps, store=store)
    assert st.status == WorkflowStatus.SUSPENDED
    assert ran == ["s1"]  # s2 لم يُنفَّذ (معلّق بانتظار حدث خارجيّ)

    st2 = run_workflow("wf2", steps, store=store)
    assert st2.status == WorkflowStatus.COMPLETED
    assert ran == ["s1", "s2"]  # استؤنف من بعد المعلّقة، بلا إعادة s1


def test_conditional_suspend_does_not_halt_when_not_needed():
    store = InMemoryWorkflowStore()
    # تعليق مشروط: يُعلّق فقط لو needs_approval في السياق.
    steps = [
        WorkflowStep("s1", lambda ctx: {}, suspends=lambda ctx: ctx.get("needs_approval", False))
    ]
    st = run_workflow("wf3", steps, store=store, initial_context={"needs_approval": False})
    assert st.status == WorkflowStatus.COMPLETED  # لا تعليق بلا داعٍ


def test_saga_compensation_undoes_completed_steps_in_reverse():
    store = InMemoryWorkflowStore()
    undone: list[str] = []

    steps = [
        WorkflowStep(
            "s1", lambda ctx: {"booked": True}, compensate=lambda ctx: undone.append("s1")
        ),
        WorkflowStep(
            "s2", lambda ctx: {"charged": True}, compensate=lambda ctx: undone.append("s2")
        ),
        WorkflowStep("s3", lambda ctx: (_ for _ in ()).throw(RuntimeError("boom"))),
    ]
    st = run_workflow("wf4", steps, store=store, compensate_on_failure=True)
    assert st.status == WorkflowStatus.COMPENSATED
    assert undone == ["s2", "s1"]  # عكسيّاً: آخر ما اكتمل يُعوَّض أوّلاً


def test_completed_workflow_is_terminal_not_rerun():
    store = InMemoryWorkflowStore()
    calls = {"n": 0}
    steps = [WorkflowStep("s1", lambda ctx: calls.__setitem__("n", calls["n"] + 1) or {})]
    run_workflow("wf5", steps, store=store)
    run_workflow("wf5", steps, store=store)  # إعادة بعد الاكتمال
    assert calls["n"] == 1  # لا يُعاد تشغيل workflow مكتمل
