"""اختبارات تدفّق تصعيد الآفة (HIL) — بوّابة الموافقة قبل الرشّ (سلامة).

فجوة تغطية حرجة (مراجعة الجولة ٣): تدفّق يقود قرار **رشّ مبيد** خلف موافقة خبير
(suspend). كان بلا اختبار ⇒ خطر تنفيذ رشّ بلا موافقة. هنا نقفل: شدّة عالية تُعلّق
(لا رشّ)، الاستئناف بعد الموافقة يُنفّذ، والشدّة المنخفضة لا تُصعّد ولا تَرشّ.
"""

import pytest
from core.pest_escalation_flow import (
    ESCALATION_TABLE,
    EXECUTION_NOT_CONFIRMED,
    EXECUTION_REF_MISSING,
    EXECUTOR_NOT_CONFIGURED,
    build_pest_escalation_steps,
    is_execution_proven,
    run_pest_escalation,
)
from core.workflow_engine import InMemoryWorkflowStore, WorkflowStatus, WorkflowStep, run_workflow

pytestmark = pytest.mark.unit

# حكم سلامة مُسمَح (W0-01): التنفيذ يتطلّب بوّابة guardrails تسمح صراحةً. الاختبارات التي
# تقيس مسار التنفيذ نفسه تحقنه؛ اختبارات الحجب في test_pest_guardrails_gate.py.
_ALLOW = {"allowed": True, "status": "allowed", "reason_ar": "سمح"}


def _allow_gate(ctx):
    return dict(_ALLOW)


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
        safety_gate_fn=_allow_gate,
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


# ── الجدول التصريحي (declarative table) يقود نفس النتائج ──


def _steps_by_id(**kwargs) -> dict:
    return {s.step_id: s for s in build_pest_escalation_steps(**kwargs)}


def test_escalation_table_thresholds_match_legacy_values():
    # العتبات والمصفوفة تصريحيّة وبقيم السلوك السابق حرفيّاً (حفظ السلوك).
    assert ESCALATION_TABLE["severity_critical"] == 0.7
    assert ESCALATION_TABLE["severity_intervention"] == 0.4
    assert ESCALATION_TABLE["approval_cleared"] == frozenset({"approved", "not_required"})
    # نطاقان: حرج→رشّ عاجل، ثمّ تدخّل→مكافحة حيويّة، مرتّبان تنازليّاً.
    bands = ESCALATION_TABLE["action_bands"]
    assert [(b[0], b[1]) for b in bands] == [(0.7, "urgent_spray"), (0.4, "biocontrol")]


def test_confirm_step_uses_table_thresholds():
    confirm = _steps_by_id()["confirm"].fn
    # عند العتبة الحرجة فأعلى ⇒ critical + مؤكَّد
    assert confirm({"severity": 0.7}) == {"alert_level": "critical", "confirmed": True}
    assert confirm({"severity": 0.95}) == {"alert_level": "critical", "confirmed": True}
    # عند عتبة التدخّل وحتى دون الحرج ⇒ warning + مؤكَّد
    assert confirm({"severity": 0.4}) == {"alert_level": "warning", "confirmed": True}
    assert confirm({"severity": 0.69}) == {"alert_level": "warning", "confirmed": True}
    # دون عتبة التدخّل ⇒ info + غير مؤكَّد (لا تصعيد)
    assert confirm({"severity": 0.39}) == {"alert_level": "info", "confirmed": False}
    assert confirm({"severity": 0.0}) == {"alert_level": "info", "confirmed": False}


def test_recommend_step_action_matrix_matches_legacy():
    recommend = _steps_by_id()["recommend"].fn
    # حرج مؤكَّد ⇒ رشّ عاجل
    urgent = recommend({"confirmed": True, "severity": 0.8})
    assert urgent["action_type"] == "urgent_spray"
    assert urgent["recommendation_ar"] == "مكافحة عاجلة — رشّ موجّه + عزل البؤرة"
    # تدخّل مؤكَّد دون الحرج ⇒ مكافحة حيويّة
    bio = recommend({"confirmed": True, "severity": 0.5})
    assert bio["action_type"] == "biocontrol"
    assert bio["recommendation_ar"] == "مراقبة مكثّفة + مكافحة حيويّة وقائيّة"
    # غير مؤكَّد ⇒ لا تصعيد
    none = recommend({"confirmed": False, "severity": 0.5})
    assert none["action_type"] == "none"
    assert none["recommendation_ar"] == "لا تصعيد — الشدّة دون عتبة التدخّل"


# ── خطوة الموافقة (await_approval) — قلب التعليق المشروط (HIL) ──


def test_await_approval_not_required_when_unconfirmed():
    # شدّة غير مؤكَّدة ⇒ لا طلب موافقة أصلاً (لا نُعلّق بلا داعٍ). نقفل أنّ
    # حالة الموافقة تصبح not_required صراحةً (مسار «لا تصعيد» لا ينتظر خبيراً).
    await_approval = _steps_by_id()["await_approval"].fn
    res = await_approval({"confirmed": False})
    assert res == {"approval_requested": False, "approval_status": "not_required"}


def test_await_approval_pending_when_confirmed_without_status():
    # شدّة مؤكَّدة بلا موافقة واصلة ⇒ يُطلَب وتبقى pending (تُحرّك التعليق المشروط).
    await_approval = _steps_by_id()["await_approval"].fn
    res = await_approval({"confirmed": True})
    assert res == {"approval_requested": True, "approval_status": "pending"}


def test_await_approval_passes_through_supplied_status_on_resume():
    # عند الاستئناف تصل موافقة الخبير عبر السياق ⇒ الخطوة تمرّرها كما هي
    # (approved)، فلا تُعاد لـpending. هذا ما يفكّ التعليق ويسمح بالتنفيذ.
    await_approval = _steps_by_id()["await_approval"].fn
    res = await_approval({"confirmed": True, "approval_status": "approved"})
    assert res == {"approval_requested": True, "approval_status": "approved"}


def test_suspend_predicate_only_holds_for_pending():
    # حارس التعليق المشروط (suspends): يُعلّق فقط حين الموافقة فعلاً معلّقة.
    # approved أو not_required لا يُعلّقان (لا استئناف بلا معنى).
    await_step = _steps_by_id()["await_approval"]
    assert await_step.suspends({"approval_status": "pending"}) is True
    assert await_step.suspends({"approval_status": "approved"}) is False
    assert await_step.suspends({"approval_status": "not_required"}) is False
    # غياب الحالة تماماً ⇒ يُعامَل كمعلّق (ليس ضمن المُخلَّصة) — تعليق دفاعيّ.
    assert await_step.suspends({}) is True


# ── خطوة التنفيذ (execute) — بوّابة HIL على مستوى الخطوة (سلامة الرشّ) ──


def test_execute_refuses_while_pending_no_side_effect():
    # بوّابة HIL الفعليّة: الموافقة pending ⇒ لا تنفيذ، ولا تُستدعى execute_fn
    # (لا أثر جانبي). نقفل الرسالة الصادقة «بانتظار موافقة الخبير».
    called: list[int] = []
    execute = _steps_by_id(execute_fn=lambda ctx: called.append(1) or {"executed": True})[
        "execute"
    ].fn
    res = execute({"approval_status": "pending", "action_type": "urgent_spray"})
    assert res == {"executed": False, "note_ar": "بانتظار موافقة الخبير — لم يُنفَّذ"}
    assert called == []  # لم تُستدعَ دالّة التنفيذ ⇒ لا رشّ


def test_execute_no_action_when_action_type_is_none():
    # موافقة مُخلَّصة لكن لا إجراء (action_type="none" أو غائب) ⇒ لا تنفيذ
    # مع إعلان صادق «لا إجراء للتنفيذ» (لا execution_ref وهميّ).
    execute = _steps_by_id()["execute"].fn
    assert execute({"approval_status": "not_required", "action_type": "none"}) == {
        "executed": False,
        "note_ar": "لا إجراء للتنفيذ",
    }
    assert execute({"approval_status": "approved", "action_type": None}) == {
        "executed": False,
        "note_ar": "لا إجراء للتنفيذ",
    }


def test_execute_without_executor_is_not_executed():
    # PEST-EXECUTE-DEFAULT-ACK-01: بلا execute_fn لم يُنفَّذ شيء. كان الخادم يعلن
    # executed=True بمرجع مختلَق exec-<action_type> فتُجدوَل متابعة لرشّ لم يقع.
    execute = _steps_by_id(safety_gate_fn=_allow_gate)["execute"].fn
    res = execute({"approval_status": "approved", "action_type": "urgent_spray"})
    assert res["executed"] is False, f"no executor must not count as executed: {res}"
    assert res["reason"] == EXECUTOR_NOT_CONFIGURED, res
    assert res["execution_ref"] is None, f"no made-up execution_ref: {res}"
    assert "exec-urgent_spray" not in repr(res), f"placeholder ref leaked: {res}"
    assert res["note_ar"].strip(), f"an Arabic note must explain why: {res}"
    assert res["guardrails"] == _ALLOW, res


def test_execute_with_proven_executor_result():
    # الضابط الموجب: executed is True مع مرجع غير فارغ ⇒ تنفيذ مُثبَت.
    execute = _steps_by_id(
        execute_fn=lambda ctx: {"executed": True, "execution_ref": "job-42"},
        safety_gate_fn=_allow_gate,
    )["execute"].fn
    res = execute({"approval_status": "approved", "action_type": "urgent_spray"})
    assert res == {"executed": True, "execution_ref": "job-42", "guardrails": _ALLOW}, res


def test_execute_honours_execute_fn_reporting_failure():
    # صدق: لو أبلغت execute_fn فشلاً (executed=False) لا نزيّفه نجاحاً. المرجع يبقى
    # ليتمكّن تعويض Saga من إلغاء أثر جزئيّ.
    execute = _steps_by_id(
        execute_fn=lambda ctx: {"executed": False, "execution_ref": "ref-9"},
        safety_gate_fn=_allow_gate,
    )["execute"].fn
    res = execute({"approval_status": "approved", "action_type": "biocontrol"})
    assert res["executed"] is False, res
    assert res["execution_ref"] == "ref-9", res
    assert res["reason"] == EXECUTION_NOT_CONFIRMED, res


@pytest.mark.parametrize(
    "executor_result",
    [
        {},  # كان bool(res.get("executed", True)) يعدّ غياب الحقل نجاحاً
        {"execution_ref": "job-1"},  # مرجع بلا إقرار صريح
        {"executed": 1, "execution_ref": "job-1"},  # truthy ليس True حرفيّاً
        {"executed": "true", "execution_ref": "job-1"},
        None,  # ليس dict
    ],
)
def test_execute_without_explicit_ack_is_not_executed(executor_result):
    execute = _steps_by_id(
        execute_fn=lambda ctx: executor_result,
        safety_gate_fn=_allow_gate,
    )["execute"].fn
    res = execute({"approval_status": "approved", "action_type": "urgent_spray"})
    assert res["executed"] is False, f"{executor_result!r} must not count as executed: {res}"
    assert res["reason"] == EXECUTION_NOT_CONFIRMED, res


@pytest.mark.parametrize("ref", [None, "", "   ", 42])
def test_execute_ack_without_execution_ref_is_not_executed(ref):
    result = {"executed": True} if ref is None else {"executed": True, "execution_ref": ref}
    execute = _steps_by_id(execute_fn=lambda ctx: result, safety_gate_fn=_allow_gate)["execute"].fn
    res = execute({"approval_status": "approved", "action_type": "urgent_spray"})
    assert res["executed"] is False, f"executed True without a ref is unproven: {res}"
    assert res["reason"] == EXECUTION_REF_MISSING, res
    assert res["execution_ref"] is None, res


def test_is_execution_proven_requires_true_and_ref():
    assert is_execution_proven({"executed": True, "execution_ref": "j"}) is True, "proven"
    assert is_execution_proven({"executed": True}) is False, "no ref ⇒ unproven"
    assert is_execution_proven({"executed": 1, "execution_ref": "j"}) is False, "1 is not True"
    assert is_execution_proven({"executed": True, "execution_ref": " "}) is False, "blank ref"
    assert is_execution_proven(None) is False, "None is unproven"


# ── خطوة المتابعة (follow_up) — تُجدوَل فقط إثر تنفيذ مُثبَت ──


def test_follow_up_skipped_when_not_executed():
    # لم يُنفَّذ ⇒ لا متابعة (لا نجدوِل لما لم يقع).
    follow_up = _steps_by_id()["follow_up"].fn
    assert follow_up({"executed": False}) == {"follow_up_scheduled": False}, "not executed"


@pytest.mark.parametrize(
    "ctx",
    [
        {"executed": True},  # بلا مرجع
        {"executed": True, "execution_ref": ""},
        {"executed": 1, "execution_ref": "job-1"},
        {"executed": "yes", "execution_ref": "job-1"},
    ],
)
def test_follow_up_skipped_without_proven_execution(ctx):
    follow_up = _steps_by_id()["follow_up"].fn
    assert follow_up(ctx) == {"follow_up_scheduled": False}, f"unproven execution: {ctx}"


def test_follow_up_scheduled_after_execution():
    # نُفِّذ فعلاً (إقرار + مرجع) ⇒ تُجدوَل متابعة (7 أيّام) للتحقّق من تراجع الإصابة.
    follow_up = _steps_by_id()["follow_up"].fn
    res = follow_up({"executed": True, "execution_ref": "job-42"})
    assert res["follow_up_scheduled"] is True, res
    assert res["follow_up_note_ar"] == "متابعة بعد 7 أيّام للتحقّق من تراجع الإصابة", res


# ── تعويض Saga يبقى عاملاً ──


def _run_with_failing_tail(execute_fn, cancel_fn, wf_id):
    steps = build_pest_escalation_steps(
        execute_fn=execute_fn, cancel_fn=cancel_fn, safety_gate_fn=_allow_gate
    )

    def _boom(ctx):
        raise RuntimeError("later step failed")

    steps.append(WorkflowStep("after_follow_up", _boom))
    return run_workflow(
        wf_id,
        steps,
        store=InMemoryWorkflowStore(),
        initial_context={"pest_type": "locust", "severity": 0.9, "approval_status": "approved"},
        compensate_on_failure=True,
    )


def test_compensation_cancels_a_proven_execution():
    cancelled: list[str] = []
    st = _run_with_failing_tail(
        lambda ctx: {"executed": True, "execution_ref": "job-7"},
        lambda ctx: cancelled.append(ctx["execution_ref"]),
        "pe_saga",
    )
    assert st.status == WorkflowStatus.COMPENSATED, st.status
    assert cancelled == ["job-7"], f"the proven execution must be cancelled: {cancelled}"


def test_compensation_skips_cancel_when_nothing_ran():
    cancelled: list[object] = []
    st = _run_with_failing_tail(None, lambda ctx: cancelled.append(1), "pe_saga_none")
    assert st.status == WorkflowStatus.COMPENSATED, st.status
    assert cancelled == [], "nothing executed ⇒ nothing to cancel"


# ── تدفّقات كاملة لنطاقات لم تُغطَّ طرفيّاً ──


def test_mid_severity_biocontrol_full_flow_after_approval():
    # نطاق التدخّل (0.4 ≤ شدّة < 0.7): يُعلَّق ثمّ بعد الموافقة يُنفَّذ مكافحةً
    # حيويّة بمرجع المنفّذ، وتُجدوَل المتابعة → COMPLETED.
    store = InMemoryWorkflowStore()
    run_pest_escalation(
        "pe_bio",
        store=store,
        initial_context={"pest_type": "mite", "severity": 0.5},
    )
    st = run_pest_escalation(
        "pe_bio",
        store=store,
        initial_context={"approval_status": "approved"},
        execute_fn=lambda ctx: {"executed": True, "execution_ref": "bio-1"},
        safety_gate_fn=_allow_gate,
    )
    assert st.status == WorkflowStatus.COMPLETED, st.status
    assert st.step_results["recommend"]["action_type"] == "biocontrol", st.step_results
    assert st.step_results["execute"] == {
        "executed": True,
        "execution_ref": "bio-1",
        "guardrails": _ALLOW,
    }, st.step_results["execute"]
    assert st.step_results["follow_up"]["follow_up_scheduled"] is True, st.step_results


def test_approved_flow_without_executor_schedules_no_follow_up():
    # PEST-EXECUTE-DEFAULT-ACK-01 طرفيّاً: موافقة + بوّابة تسمح لكن لا منفّذ ⇒ لم يُنفَّذ،
    # ولا متابعة 7 أيّام لرشّ لم يقع.
    store = InMemoryWorkflowStore()
    run_pest_escalation("pe_noexec", store=store, initial_context={"severity": 0.9})
    st = run_pest_escalation(
        "pe_noexec",
        store=store,
        initial_context={"approval_status": "approved"},
        safety_gate_fn=_allow_gate,
    )
    assert st.status == WorkflowStatus.COMPLETED, st.status
    assert st.step_results["execute"]["executed"] is False, st.step_results["execute"]
    assert st.step_results["execute"]["reason"] == EXECUTOR_NOT_CONFIGURED, st.step_results
    assert st.step_results["follow_up"] == {"follow_up_scheduled": False}, st.step_results


def test_low_severity_flow_records_no_action_execute():
    # دون عتبة التدخّل: يكتمل بلا تعليق، وخطوة التنفيذ تُعلن «لا إجراء للتنفيذ»
    # (action_type=none رغم أنّ الموافقة not_required) ولا تُجدوَل متابعة.
    store = InMemoryWorkflowStore()
    st = run_pest_escalation(
        "pe_low",
        store=store,
        initial_context={"pest_type": "aphid", "severity": 0.2},
    )
    assert st.status == WorkflowStatus.COMPLETED
    assert st.step_results["await_approval"]["approval_status"] == "not_required"
    assert st.step_results["execute"] == {
        "executed": False,
        "note_ar": "لا إجراء للتنفيذ",
    }
    assert st.step_results["follow_up"] == {"follow_up_scheduled": False}


def test_detect_step_default_reads_context_and_coerces_severity():
    # بلا detect_fn: الرصد يقرأ من السياق ويُحوّل الشدّة لـfloat (متانة المدخل).
    detect = _steps_by_id()["detect"].fn
    assert detect({"pest_type": "locust", "severity": "0.5"}) == {
        "pest_type": "locust",
        "severity": 0.5,
    }
    # غياب الحقول ⇒ افتراضات صادقة (غير محدّد / 0.0) لا انهيار.
    assert detect({}) == {"pest_type": "غير محدّد", "severity": 0.0}


def test_recommend_confirmed_below_lowest_band_falls_back_honestly():
    # مسار احتياطي صادق: «مؤكَّد» لكن دون أدنى نطاق (لا يقع عمليّاً إذ التأكيد ≥
    # عتبة التدخّل) ⇒ يُعلَن «لا تصعيد» بدل اختلاق توصية.
    recommend = _steps_by_id()["recommend"].fn
    res = recommend({"confirmed": True, "severity": 0.0})
    assert res == {
        "recommendation_ar": "لا تصعيد — الشدّة دون عتبة التدخّل",
        "action_type": "none",
    }
