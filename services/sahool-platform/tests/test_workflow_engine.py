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
    summarize_workflows,
    workflow_trace,
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


# ── مسار النجاح + تراكم السياق ─────────────────────────────────────


def test_all_success_completes_and_records_results_and_context():
    # كلّ الخطوات تنجح ⇒ COMPLETED، النتائج محفوظة، والسياق يتراكم خطوةً بخطوة.
    store = InMemoryWorkflowStore()
    steps = [
        WorkflowStep("s1", lambda ctx: {"a": 1}),
        # s2 يقرأ ما أنتجته s1 من السياق المتراكم — يثبت تمرير المخرجات للأمام.
        WorkflowStep("s2", lambda ctx: {"b": ctx["a"] + 1}),
    ]
    st = run_workflow("wf-ok", steps, store=store)
    assert st.status == WorkflowStatus.COMPLETED
    assert st.completed_steps == ["s1", "s2"]
    assert st.step_results == {"s1": {"a": 1}, "s2": {"b": 2}}
    assert st.context["a"] == 1 and st.context["b"] == 2  # تراكم السياق
    assert st.current_step is None  # عند الاكتمال لا توجد خطوة جارية


def test_empty_workflow_completes_immediately():
    # workflow بلا خطوات ⇒ يكتمل فوراً (لا فشل، لا حلقة فارغة عالقة).
    store = InMemoryWorkflowStore()
    st = run_workflow("wf-empty", [], store=store)
    assert st.status == WorkflowStatus.COMPLETED
    assert st.completed_steps == []
    assert st.current_step is None


def test_single_step_success_completes():
    # حالة طرفيّة: خطوة واحدة ناجحة ⇒ اكتمال + تسجيلها مكتملة.
    store = InMemoryWorkflowStore()
    st = run_workflow("wf-one", [WorkflowStep("only", lambda ctx: {"ok": True})], store=store)
    assert st.status == WorkflowStatus.COMPLETED
    assert st.completed_steps == ["only"]


# ── انتشار الفشل ومسار التعويض (Saga) ──────────────────────────────


def test_failure_without_compensation_flag_stays_failed_resumable():
    # بدون compensate_on_failure: الفشل يبقى FAILED (قابلاً للاستئناف) ولا تعويض،
    # حتّى لو وُجدت دالّة compensate على الخطوات السابقة — لا تراجع غير مطلوب.
    store = InMemoryWorkflowStore()
    undone: list[str] = []
    steps = [
        WorkflowStep("s1", lambda ctx: {"x": 1}, compensate=lambda ctx: undone.append("s1")),
        WorkflowStep("s2", lambda ctx: (_ for _ in ()).throw(RuntimeError("boom"))),
    ]
    st = run_workflow("wf-nocomp", steps, store=store, compensate_on_failure=False)
    assert st.status == WorkflowStatus.FAILED
    assert undone == []  # لم يُستدعَ أيّ تعويض
    assert st.compensated_steps == []
    assert "s2" in st.error and "boom" in st.error  # الفشل مُعلَن بوضوح


def test_failure_on_first_step_does_not_compensate():
    # الفشل على أوّل خطوة (لا خطوات مكتملة) ⇒ لا شيء لتعويضه؛ يبقى FAILED لا
    # COMPENSATED رغم رفع علم التعويض (شرط state.completed_steps فارغ).
    store = InMemoryWorkflowStore()
    undone: list[str] = []
    steps = [
        WorkflowStep(
            "s1",
            lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")),
            compensate=lambda ctx: undone.append("s1"),
        ),
        WorkflowStep("s2", lambda ctx: {}, compensate=lambda ctx: undone.append("s2")),
    ]
    st = run_workflow("wf-first", steps, store=store, compensate_on_failure=True)
    assert st.status == WorkflowStatus.FAILED  # لا تعويض لغياب خطوات مكتملة
    assert undone == []
    assert st.compensated_steps == []


def test_compensation_records_compensated_steps_in_reverse():
    # التعويض يُسجَّل في compensated_steps بالترتيب العكسي (لا مجرّد استدعاء جانبيّ).
    store = InMemoryWorkflowStore()
    steps = [
        WorkflowStep("s1", lambda ctx: {}, compensate=lambda ctx: None),
        WorkflowStep("s2", lambda ctx: {}, compensate=lambda ctx: None),
        WorkflowStep("s3", lambda ctx: (_ for _ in ()).throw(RuntimeError("x"))),
    ]
    st = run_workflow("wf-rec", steps, store=store, compensate_on_failure=True)
    assert st.status == WorkflowStatus.COMPENSATED
    # s3 فشلت (لم تكتمل) ⇒ لا تُعوَّض؛ المكتملتان s1,s2 تُعوَّضان عكسيّاً.
    assert st.compensated_steps == ["s2", "s1"]


def test_step_without_compensate_is_skipped_but_others_still_compensated():
    # خطوة بلا compensate غير قابلة للتعويض ⇒ تُتخطّى (لا تُسجَّل مُعوَّضة)، بينما
    # القابلات للتعويض حولها تُعوَّض عكسيّاً (صدق: لا ادّعاء تعويض لم يحدث).
    store = InMemoryWorkflowStore()
    undone: list[str] = []
    steps = [
        WorkflowStep("s1", lambda ctx: {}, compensate=lambda ctx: undone.append("s1")),
        WorkflowStep("s2", lambda ctx: {}),  # بلا compensate — غير قابلة للتعويض
        WorkflowStep("s3", lambda ctx: {}, compensate=lambda ctx: undone.append("s3")),
        WorkflowStep("s4", lambda ctx: (_ for _ in ()).throw(RuntimeError("x"))),
    ]
    st = run_workflow("wf-gap", steps, store=store, compensate_on_failure=True)
    assert st.status == WorkflowStatus.COMPENSATED
    assert undone == ["s3", "s1"]  # عكسيّاً، وتُخطَّى s2 غير القابلة للتعويض
    assert st.compensated_steps == ["s3", "s1"]  # s2 ليست مُعوَّضة


def test_failing_compensate_does_not_halt_remaining_compensations():
    # فشل دالّة تعويض واحدة لا يوقف سلسلة التعويض (نُعوّض ما نستطيع)، والخطوة
    # التي فشل تعويضها لا تُسجَّل في compensated_steps (لم يكتمل تراجعها). صدق
    # fail-loud: تُسجَّل في compensation_failures والحالة COMPENSATION_FAILED
    # (تراجع جزئيّ غير متّسق — لا تُبتلَع ولا تُدّعى COMPENSATED زائفة).
    store = InMemoryWorkflowStore()
    undone: list[str] = []

    def comp_s2_boom(ctx):
        raise RuntimeError("compensation failed")

    steps = [
        WorkflowStep("s1", lambda ctx: {}, compensate=lambda ctx: undone.append("s1")),
        WorkflowStep("s2", lambda ctx: {}, compensate=comp_s2_boom),
        WorkflowStep("s3", lambda ctx: (_ for _ in ()).throw(RuntimeError("x"))),
    ]
    st = run_workflow("wf-compfail", steps, store=store, compensate_on_failure=True)
    assert st.status == WorkflowStatus.COMPENSATION_FAILED  # تراجع جزئيّ مُعلَن
    assert undone == ["s1"]  # رغم فشل تعويض s2، استمرّ التعويض إلى s1
    assert st.compensated_steps == ["s1"]  # s2 لم تُسجَّل (تعويضها فشل)
    # فشل التعويض مُدوَّن في الحالة (لا ابتلاع صامت) — يصمد ويظهر للرصد.
    assert [f["step_id"] for f in st.compensation_failures] == ["s2"]
    assert "compensation failed" in st.compensation_failures[0]["error"]


def test_compensation_runs_exactly_once_per_step():
    # ثابت Saga: كلّ تعويض يُستدعى مرّةً واحدة بالضبط (لا تكرار للتراجع).
    store = InMemoryWorkflowStore()
    counts = {"s1": 0, "s2": 0}
    steps = [
        WorkflowStep(
            "s1", lambda ctx: {}, compensate=lambda ctx: counts.__setitem__("s1", counts["s1"] + 1)
        ),
        WorkflowStep(
            "s2", lambda ctx: {}, compensate=lambda ctx: counts.__setitem__("s2", counts["s2"] + 1)
        ),
        WorkflowStep("s3", lambda ctx: (_ for _ in ()).throw(RuntimeError("x"))),
    ]
    st = run_workflow("wf-once", steps, store=store, compensate_on_failure=True)
    assert st.status == WorkflowStatus.COMPENSATED
    assert counts == {"s1": 1, "s2": 1}


def test_compensated_workflow_is_terminal_not_rerun():
    # COMPENSATED حالة نهائيّة: إعادة التشغيل لا تُنفّذ خطوات ولا تُعيد التعويض.
    store = InMemoryWorkflowStore()
    undone: list[str] = []
    body_calls = {"s1": 0}

    def s1(ctx):
        body_calls["s1"] += 1
        return {}

    steps = [
        WorkflowStep("s1", s1, compensate=lambda ctx: undone.append("s1")),
        WorkflowStep("s2", lambda ctx: (_ for _ in ()).throw(RuntimeError("x"))),
    ]
    run_workflow("wf-term", steps, store=store, compensate_on_failure=True)
    st2 = run_workflow("wf-term", steps, store=store, compensate_on_failure=True)
    assert st2.status == WorkflowStatus.COMPENSATED
    assert body_calls["s1"] == 1  # لم تُعَد s1
    assert undone == ["s1"]  # التعويض لم يتكرّر عند إعادة التشغيل


# ── عدم تطابق نسخة التعريف عند الاستئناف ───────────────────────────


def test_version_mismatch_on_resume_fails_loud_without_running_steps():
    # استئناف بنسخة تعريف مختلفة عن المحفوظة ⇒ FAILED مُعلَن، دون تنفيذ خطوات.
    store = InMemoryWorkflowStore()
    ran: list[str] = []
    v1_steps = [
        WorkflowStep("s1", lambda ctx: ran.append("s1") or {}, suspends=True),
        WorkflowStep("s2", lambda ctx: ran.append("s2") or {}),
    ]
    st1 = run_workflow("wf-ver", v1_steps, store=store, workflow_version="1")
    assert st1.status == WorkflowStatus.SUSPENDED
    assert ran == ["s1"]
    # استئناف بنسخة "2" مختلفة ⇒ يُعلَن عدم التطابق ولا يُنفَّذ s2.
    st2 = run_workflow("wf-ver", v1_steps, store=store, workflow_version="2")
    assert st2.status == WorkflowStatus.FAILED
    assert ran == ["s1"]  # لم تُنفَّذ أيّ خطوة جديدة
    assert "2" in st2.error and "1" in st2.error  # رسالة عدم التطابق واضحة


# ── الرصد (observability) ──────────────────────────────────────────


def test_workflow_trace_reports_failure_needs_attention_and_stalled():
    # أثر الفشل: needs_attention + is_stalled صحيحان، والخطأ والخطوة الجارية مُبلَّغة.
    store = InMemoryWorkflowStore()
    steps = [
        WorkflowStep("s1", lambda ctx: {}),
        WorkflowStep("s2", lambda ctx: (_ for _ in ()).throw(RuntimeError("boom"))),
    ]
    st = run_workflow("wf-trace", steps, store=store)
    tr = workflow_trace(st)
    assert tr["status"] == "failed"
    assert tr["completed_steps"] == ["s1"]
    assert tr["steps_done"] == 1
    assert tr["current_step"] == "s2"  # توقّف عند الخطوة الفاشلة
    assert tr["is_stalled"] is True
    assert tr["needs_attention"] is True


def test_workflow_trace_compensated_lists_compensated_not_needing_attention():
    # أثر التعويض: compensated_steps مُبلَّغة وليس عالقاً/يحتاج انتباهاً (تراجع تمّ).
    store = InMemoryWorkflowStore()
    steps = [
        WorkflowStep("s1", lambda ctx: {}, compensate=lambda ctx: None),
        WorkflowStep("s2", lambda ctx: (_ for _ in ()).throw(RuntimeError("x"))),
    ]
    st = run_workflow("wf-trc", steps, store=store, compensate_on_failure=True)
    tr = workflow_trace(st)
    assert tr["status"] == "compensated"
    assert tr["compensated_steps"] == ["s1"]
    assert tr["is_stalled"] is False  # COMPENSATED ليست عالقة
    assert tr["needs_attention"] is False


def test_summarize_counts_by_status_and_flags_stalled():
    # ملخّص جماعي: عدّ حسب الحالة، رصد العالقة (FAILED/SUSPENDED)، وعلَم الانتباه.
    store = InMemoryWorkflowStore()
    ok = run_workflow("ok", [WorkflowStep("a", lambda c: {})], store=store)
    failed = run_workflow(
        "bad",
        [WorkflowStep("a", lambda c: (_ for _ in ()).throw(RuntimeError("x")))],
        store=store,
    )
    suspended = run_workflow("susp", [WorkflowStep("a", lambda c: {}, suspends=True)], store=store)
    summary = summarize_workflows([ok, failed, suspended])
    assert summary["total"] == 3
    assert summary["by_status"]["completed"] == 1
    assert summary["by_status"]["failed"] == 1
    assert summary["by_status"]["suspended"] == 1
    assert set(summary["stalled_workflows"]) == {"bad", "susp"}  # العالقة فقط
    assert summary["needs_attention"] is True  # وجود failed يرفع العلم
