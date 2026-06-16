"""اختبارات تدفّق تصعيد الآفة (HIL) — بوّابة الموافقة قبل الرشّ (سلامة).

فجوة تغطية حرجة (مراجعة الجولة ٣): تدفّق يقود قرار **رشّ مبيد** خلف موافقة خبير
(suspend). كان بلا اختبار ⇒ خطر تنفيذ رشّ بلا موافقة. هنا نقفل: شدّة عالية تُعلّق
(لا رشّ)، الاستئناف بعد الموافقة يُنفّذ، والشدّة المنخفضة لا تُصعّد ولا تَرشّ.
"""

from core.pest_escalation_flow import (
    ESCALATION_TABLE,
    build_pest_escalation_steps,
    run_pest_escalation,
)
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


def test_execute_default_ref_when_no_execute_fn():
    # بلا execute_fn محقونة وبموافقة معتمَدة وإجراء فعليّ ⇒ تنفيذ افتراضي
    # ومرجع مشتقّ من نوع الإجراء (exec-<action_type>) — لا تبعيّة حيّة.
    execute = _steps_by_id()["execute"].fn
    res = execute({"approval_status": "approved", "action_type": "urgent_spray"})
    assert res == {"executed": True, "execution_ref": "exec-urgent_spray"}


def test_execute_honours_execute_fn_reporting_failure():
    # صدق: لو أبلغت execute_fn فشلاً (executed=False) لا نزيّفه نجاحاً.
    execute = _steps_by_id(execute_fn=lambda ctx: {"executed": False, "execution_ref": "ref-9"})[
        "execute"
    ].fn
    res = execute({"approval_status": "approved", "action_type": "biocontrol"})
    assert res == {"executed": False, "execution_ref": "ref-9"}


# ── خطوة المتابعة (follow_up) — تُجدوَل فقط إثر تنفيذ فعلي ──


def test_follow_up_skipped_when_not_executed():
    # لم يُنفَّذ ⇒ لا متابعة (لا نجدوِل لما لم يقع).
    follow_up = _steps_by_id()["follow_up"].fn
    assert follow_up({"executed": False}) == {"follow_up_scheduled": False}


def test_follow_up_scheduled_after_execution():
    # نُفِّذ ⇒ تُجدوَل متابعة (7 أيّام) للتحقّق من تراجع الإصابة.
    follow_up = _steps_by_id()["follow_up"].fn
    res = follow_up({"executed": True})
    assert res["follow_up_scheduled"] is True
    assert res["follow_up_note_ar"] == "متابعة بعد 7 أيّام للتحقّق من تراجع الإصابة"


# ── تدفّقات كاملة لنطاقات لم تُغطَّ طرفيّاً ──


def test_mid_severity_biocontrol_full_flow_after_approval():
    # نطاق التدخّل (0.4 ≤ شدّة < 0.7): يُعلَّق ثمّ بعد الموافقة يُنفَّذ مكافحةً
    # حيويّة بمرجع افتراضي exec-biocontrol، وتُجدوَل المتابعة → COMPLETED.
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
    )
    assert st.status == WorkflowStatus.COMPLETED
    assert st.step_results["recommend"]["action_type"] == "biocontrol"
    assert st.step_results["execute"] == {
        "executed": True,
        "execution_ref": "exec-biocontrol",
    }
    assert st.step_results["follow_up"]["follow_up_scheduled"] is True


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
