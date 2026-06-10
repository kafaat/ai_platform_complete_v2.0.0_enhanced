"""Unit tests (CI-enforced) for the incorporated production modules:
workflow_engine, correlation, irrigation_water_analysis, pest_escalation_flow.

الـzip أضاف هذه الوحدات + فحوص roadmap غير مُعلَّمة (تُستبعَد في CI). هذه
الاختبارات تحرسها فعليّاً بـassert ومُعلَّمة unit (تقوية: تُشغَّل وتُفشِل CI عند
الانتكاس).
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


def _load(name: str, rel: str):
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── irrigation_water_analysis ───────────────────────────────────────────
def _iwa():
    return _load(
        "irrigation_water_analysis", "services/sahool-platform/core/irrigation_water_analysis.py"
    )


@pytest.mark.unit
def test_sar_rsc_formulas_correct():
    iwa = _iwa()
    # SAR = Na/√((Ca+Mg)/2): 10/√2 = 7.071
    assert abs(iwa.compute_sar(10, 2, 2) - 7.071) < 0.01
    # RSC = (CO3+HCO3) − (Ca+Mg): (0+5) − (2+1) = 2
    assert iwa.compute_rsc(0, 5, 2, 1) == 2


@pytest.mark.unit
def test_water_classification_and_full_analysis():
    iwa = _iwa()
    assert iwa.classify_sar(20)["class"] != iwa.classify_sar(2)["class"]  # high vs low
    sample = iwa.WaterSample(sample_id="w1", source="well", na=10, ca=2, mg=2, hco3=5, co3=0)
    res = iwa.analyze_water_sample(sample)
    assert "indices" in res and "classification" in res
    assert abs(res["indices"]["sar"] - 7.071) < 0.01


# ── correlation ─────────────────────────────────────────────────────────
def _cor():
    return _load("correlation", "services/sahool-platform/core/correlation.py")


@pytest.mark.unit
def test_correlation_id_and_headers_roundtrip():
    cor = _cor()
    a, b = cor.new_correlation_id(), cor.new_correlation_id()
    assert a != b and a.startswith("corr-")
    cid = cor.set_correlation("corr-test")
    assert cid == "corr-test" and cor.get_correlation_id() == "corr-test"
    headers = cor.correlation_headers()
    cor.set_correlation()  # reset to a fresh id
    restored = cor.from_headers(headers)
    assert restored == "corr-test"  # propagated across a "service hop"


@pytest.mark.unit
def test_build_trace_tree_roots_and_orphans():
    cor = _cor()
    links = [
        cor.TraceLink(kind="workflow", entity_id="wf", correlation_id="c", causation_id=None),
        cor.TraceLink(kind="command", entity_id="cmd", correlation_id="c", causation_id="wf"),
        cor.TraceLink(kind="event", entity_id="ev", correlation_id="c", causation_id="ghost"),
    ]
    tree = cor.build_trace_tree(links)
    assert "wf" in tree["roots"]
    assert tree["orphans"] == ["ev"]  # سبب مفقود يُعلَن بصدق


# ── workflow_engine ─────────────────────────────────────────────────────
def _wfe():
    return _load("workflow_engine", "services/sahool-platform/core/workflow_engine.py")


@pytest.mark.unit
def test_workflow_runs_and_resumes_idempotently():
    wfe = _wfe()
    calls: list = []
    steps = [
        wfe.WorkflowStep(step_id="s1", fn=lambda ctx: calls.append("s1") or {"a": 1}),
        wfe.WorkflowStep(step_id="s2", fn=lambda ctx: calls.append("s2") or {"b": 2}),
    ]
    store = wfe.InMemoryWorkflowStore()
    st = wfe.run_workflow("wf1", steps, store=store, tenant_id="t1")
    assert st.status.value == "completed" and calls == ["s1", "s2"]
    # إعادة التشغيل تتخطّى المكتمل (durability/idempotency) — لا يُعاد تنفيذ الخطوات
    wfe.run_workflow("wf1", steps, store=store, tenant_id="t1")
    assert calls == ["s1", "s2"]


@pytest.mark.unit
def test_workflow_suspends_for_external_resume():
    wfe = _wfe()
    ran: list = []
    steps = [
        wfe.WorkflowStep(step_id="detect", fn=lambda ctx: ran.append("detect") or {}),
        wfe.WorkflowStep(
            step_id="approve", fn=lambda ctx: ran.append("approve") or {}, suspends=True
        ),
        wfe.WorkflowStep(step_id="execute", fn=lambda ctx: ran.append("execute") or {}),
    ]
    store = wfe.InMemoryWorkflowStore()
    st = wfe.run_workflow("wf2", steps, store=store, tenant_id="t1")
    assert st.status.value == "suspended"
    assert "execute" not in ran  # يتوقّف عند الموافقة، لا يُنفّذ ما بعدها


# ── pest_escalation_flow (يجمع workflow_engine + alert_engine + correlation) ──
@pytest.mark.unit
def test_pest_escalation_flow_builds_and_runs():
    pef = _load("pest_escalation_flow", "services/sahool-platform/core/pest_escalation_flow.py")
    assert callable(pef.build_pest_escalation_steps)
    assert callable(pef.run_pest_escalation)
    steps = pef.build_pest_escalation_steps()
    # duck-typed (WorkflowStep قد يكون نسخة وحدة مختلفة عبر التحميل المنفصل)
    assert steps and all(hasattr(s, "step_id") and hasattr(s, "fn") for s in steps)
    assert any(getattr(s, "suspends", False) for s in steps)  # خطوة موافقة بشريّة


@pytest.mark.unit
def test_workflow_resume_merges_initial_context():
    """الاستئناف يدمج المدخل الخارجي في السياق (قناة التعليق/الاستئناف).

    قبل الإصلاح كان initial_context يُهمَل عند الاستئناف ⇒ موافقة الخبير (أو أيّ
    إدخال) لا تصل للخطوات بعد التعليق فيُصبح التعليق بلا فائدة.
    """
    wfe = _wfe()
    seen: dict = {}
    steps = [
        wfe.WorkflowStep(step_id="gate", fn=lambda ctx: {"v": 1}, suspends=True),
        wfe.WorkflowStep(step_id="use", fn=lambda ctx: seen.update(ext=ctx.get("ext")) or {}),
    ]
    store = wfe.InMemoryWorkflowStore()
    st = wfe.run_workflow("wfm", steps, store=store, tenant_id="t1")
    assert st.status.value == "suspended" and "ext" not in seen
    # استئناف بمدخل خارجي ⇒ يصل للخطوة التالية (كان يُهمَل قبل الإصلاح)
    wfe.run_workflow("wfm", steps, store=store, tenant_id="t1", initial_context={"ext": "hello"})
    assert seen.get("ext") == "hello"


@pytest.mark.unit
def test_workflow_compensated_is_terminal():
    """الحالة المُعوَّضة (Saga) نهائيّة لا تُعاد. قبل الإصلاح كان COMPENSATED
    يُعاد تشغيله (يُهمَل تعويضه) ⇒ خطر تنفيذ مزدوج بعد التراجع."""
    wfe = _wfe()
    calls: list = []

    def _boom(ctx):
        raise RuntimeError("fail")

    steps = [
        wfe.WorkflowStep(
            step_id="ok",
            fn=lambda ctx: calls.append("ok") or {},
            compensate=lambda ctx: calls.append("undo"),
        ),
        wfe.WorkflowStep(step_id="bad", fn=_boom),
    ]
    store = wfe.InMemoryWorkflowStore()
    st = wfe.run_workflow("wfc", steps, store=store, tenant_id="t1", compensate_on_failure=True)
    assert st.status.value == "compensated" and calls == ["ok", "undo"]
    # إعادة التشغيل لا تُعيد المُعوَّض (نهائيّ) — لا تنفيذ/تعويض إضافي
    wfe.run_workflow("wfc", steps, store=store, tenant_id="t1", compensate_on_failure=True)
    assert calls == ["ok", "undo"]


@pytest.mark.unit
def test_pest_hil_executes_only_after_approval():
    """HIL فعليّ: لا تنفيذ قبل موافقة الخبير، وينفّذ بعدها فقط.

    يثبت الإصلاحين معاً: التعليق قبل التنفيذ (لا HIL شكليّ) + دمج الموافقة عند
    الاستئناف عبر initial_context (وإلّا لا تصل الموافقة لخطوة التنفيذ)."""
    pef = _load("pest_escalation_flow", "services/sahool-platform/core/pest_escalation_flow.py")
    executed: list = []

    def execute_fn(ctx):
        executed.append(ctx.get("action_type"))
        return {"executed": True, "execution_ref": "ref-1"}

    store = pef.InMemoryWorkflowStore()
    st1 = pef.run_pest_escalation(
        "pest-hil",
        store=store,
        tenant_id="t1",
        initial_context={"pest_type": "صدأ", "severity": 0.85},
        execute_fn=execute_fn,
    )
    assert st1.status.value == "suspended"
    assert executed == []  # بوّابة HIL فعليّة: لا تنفيذ قبل الموافقة
    # استئناف بموافقة الخبير (تصل عبر دمج initial_context عند الاستئناف)
    st2 = pef.run_pest_escalation(
        "pest-hil",
        store=store,
        tenant_id="t1",
        initial_context={"approval_status": "approved"},
        execute_fn=execute_fn,
    )
    assert st2.status.value == "completed"
    assert executed == ["urgent_spray"]  # نُفّذ بعد الموافقة فقط


@pytest.mark.unit
def test_pest_no_escalation_does_not_suspend_needlessly():
    """مسار «لا تصعيد» (شدّة دون العتبة) لا يُعلّق (تعليق مشروط): يكتمل في نداء
    واحد بلا طلب استئناف بلا معنى — وبلا تنفيذ (لا إجراء)."""
    pef = _load("pest_escalation_flow", "services/sahool-platform/core/pest_escalation_flow.py")
    executed: list = []

    def execute_fn(ctx):
        executed.append(ctx.get("action_type"))
        return {"executed": True}

    store = pef.InMemoryWorkflowStore()
    st = pef.run_pest_escalation(
        "pest-low",
        store=store,
        tenant_id="t1",
        initial_context={"pest_type": "بقعة", "severity": 0.2},  # دون عتبة التأكيد
        execute_fn=execute_fn,
    )
    assert st.status.value == "completed"  # لا تعليق — اكتمل في نداء واحد
    assert executed == []  # لا تنفيذ (لا إجراء للتصعيد)
    assert st.step_results["await_approval"]["approval_status"] == "not_required"
