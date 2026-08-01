"""اختبارات الطبقة التصريحيّة لسير العمل (workflow_definitions).

تقفل العقد: تعريف workflow بياناتٌ وصفيّة + سجلّ معالِجات نصّيّ، و`build_steps`
يحلّ التعريف إلى `WorkflowStep` حقيقيّة للمحرّك، ومُعرِّف معالِج غير مسجَّل يفشل
بوضوح (fail-loud)، والتدفّق المبنيّ يكتمل فعليّاً عبر `run_workflow` (end-to-end).
"""

import pytest
from api import workflow_definitions as wd
from core.workflow_engine import (
    InMemoryWorkflowStore,
    WorkflowStatus,
    WorkflowStep,
    run_workflow,
)


def test_list_workflows_includes_irrigation_cycle_ordered_steps():
    # (أ) البيانات الوصفيّة تتضمّن irrigation_cycle بأربع خطوات مرتّبة.
    flows = {f["id"]: f for f in wd.list_workflows()}
    assert "irrigation_cycle" in flows
    assert flows["irrigation_cycle"]["step_names"] == [
        "validate",
        "schedule",
        "execute",
        "verify",
    ]


def test_build_steps_returns_workflow_steps_with_matching_names():
    # (ب) البناء يُرجِع list[WorkflowStep] بطول ٤ وأسماء خطوات مطابقة.
    defn = wd.get_workflow("irrigation_cycle")
    steps = wd.build_steps(defn)
    assert isinstance(steps, list)
    assert len(steps) == 4
    assert all(isinstance(s, WorkflowStep) for s in steps)
    assert [s.step_id for s in steps] == ["validate", "schedule", "execute", "verify"]


def test_unregistered_handler_id_raises_clear_error():
    # (ج) مُعرِّف معالِج غير مسجَّل ⇒ خطأ واضح (لا تخطٍّ صامت).
    bad = wd.WorkflowDefinition(
        id="_bad",
        name_ar="تعريف خاطئ",
        steps=(wd.StepSpec(step_name="x", handler_id="does.not.exist"),),
    )
    with pytest.raises(KeyError) as exc:
        wd.build_steps(bad)
    assert "does.not.exist" in str(exc.value)
    assert "غير مسجَّل" in str(exc.value)


def test_end_to_end_template_steps_do_not_reach_completion():
    """(د) end-to-end: الخطوات المبنيّة تُنفَّذ عبر المحرّك — والقوالب **لا** تكتمل.

    هذا الاختبار كان يؤكّد سابقاً أنّ `irrigation_cycle` يبلغ COMPLETED بخطواته
    الأربع. لكنّ العلم `FEATURE_IRRIGATION_WORKFLOW_REAL` مُطفأ افتراضاً، فالأربعة
    **قوالب** لا تفعل شيئاً (`_template=True`) — فكان الاختبار يُرمِّز «نجاحاً غير
    حقيقيّاً» ويحرسه: دورة ريّ كاملة «مكتملة» بلا تحقّق ولا جدولة ولا تنفيذ ولا
    تحقّق بعديّ.

    بعد حارس `_reject_template_result` في المحرّك، القالب يُعامَل فشلَ خطوة. التوقّع
    الصحيح إذن هو **عدم** الاكتمال، وأن يسمّي الخطأ سببه. اكتمال المسار الحقيقيّ
    (العلم مُفعَّل + سياق صالح) مُغطّى في `tests/test_irrigation_workflow_handlers.py
    ::test_real_workflow_suspends_then_resumes_with_approval` (يؤكّد COMPLETED
    و`_template is False` عند الاستئناف بموافقة).
    """
    defn = wd.get_workflow("irrigation_cycle")
    steps = wd.build_steps(defn)
    store = InMemoryWorkflowStore()
    state = run_workflow(
        "wf-irrigation-test",
        steps,
        store=store,
        tenant_id="t-test",
    )
    assert state.status == WorkflowStatus.FAILED
    assert state.completed_steps == [], "خطوة قالب سُجِّلت مكتملة — نجاح غير حقيقيّ"
    assert "_template" in (state.error or "")
