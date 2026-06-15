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


def _steps_by_id() -> dict:
    return {s.step_id: s for s in build_pest_escalation_steps()}


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
