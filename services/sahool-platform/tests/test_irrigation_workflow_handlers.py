"""اختبارات معالِجات سير عمل الريّ الحقيقيّة (workflow_definitions).

تقفل العقد للنمط المرن (FEATURE_IRRIGATION_WORKFLOW_REAL):
- validate يرفض المدخلات الناقصة بصدق (لا validated:true أعمى) ويقبل الكاملة.
- schedule حتميّ (نفس المدخلات ⇒ نفس الجدول) ويبني خطّة حقيقيّة عبر plan_irrigation.
- execute يحترم HITL (لا نيّة تنفيذ بلا موافقة معتمَدة) ولا يحرّك صمّاماً (نيّة موسومة).
- verify يقارن المُخطَّط بالمُنفَّذ.
- المعالِجات الحقيقيّة تَسِم _template=False (تمييزها عن القوالب).

المعالِجات نقيّة (لا خدمات/لا I/O) ⇒ unit. تُستدعى مباشرةً بسياق dict مثل المحرّك.
"""

import pytest
from api import workflow_definitions as wd

pytestmark = pytest.mark.unit


def _base_ctx(**overrides) -> dict:
    ctx = {
        "field_id": "field-1",
        "texture": "loam",
        "root_depth_m": 0.6,
        "forecast": [
            {"et0_mm": 6.0, "kc": 1.0, "rain_mm": 0.0},
            {"et0_mm": 6.0, "kc": 1.0, "rain_mm": 0.0},
            {"et0_mm": 6.0, "kc": 1.0, "rain_mm": 0.0},
            {"et0_mm": 6.0, "kc": 1.0, "rain_mm": 0.0},
            {"et0_mm": 6.0, "kc": 1.0, "rain_mm": 0.0},
        ],
    }
    ctx.update(overrides)
    return ctx


# ── validate: يرفض الناقص بصدق ───────────────────────────────────────────


def test_validate_accepts_complete_inputs():
    fn = wd._HANDLERS["irrigation.real.validate"]
    out = fn(_base_ctx())
    assert out["validated"] is True
    assert out["_template"] is False
    assert out["field_id"] == "field-1"


def test_validate_rejects_missing_field_id():
    fn = wd._HANDLERS["irrigation.real.validate"]
    with pytest.raises(ValueError) as exc:
        fn(_base_ctx(field_id=None))
    assert "field_id" in str(exc.value)


def test_validate_rejects_missing_texture():
    fn = wd._HANDLERS["irrigation.real.validate"]
    with pytest.raises(ValueError) as exc:
        fn(_base_ctx(texture=None))
    assert "texture" in str(exc.value) or "TAW" in str(exc.value)


def test_validate_rejects_empty_forecast():
    fn = wd._HANDLERS["irrigation.real.validate"]
    with pytest.raises(ValueError) as exc:
        fn(_base_ctx(forecast=[]))
    assert "forecast" in str(exc.value)


def test_validate_rejects_negative_budget():
    fn = wd._HANDLERS["irrigation.real.validate"]
    with pytest.raises(ValueError) as exc:
        fn(_base_ctx(season_budget_mm=-10))
    assert "season_budget_mm" in str(exc.value)


def test_validate_rejects_unknown_policy():
    fn = wd._HANDLERS["irrigation.real.validate"]
    with pytest.raises(ValueError) as exc:
        fn(_base_ctx(policy="nonsense_policy"))
    assert "policy" in str(exc.value)


# ── schedule: حتميّ + خطّة حقيقيّة ────────────────────────────────────────


def test_schedule_builds_real_plan_marked_non_template():
    fn = wd._HANDLERS["irrigation.real.schedule"]
    out = fn(_base_ctx())
    assert out["scheduled"] is True
    assert out["_template"] is False
    plan = out["irrigation_plan"]
    assert "days" in plan and len(plan["days"]) == 5
    assert plan["total_irrigation_mm"] >= 0.0
    # دفعات ريّ فعليّة تحدث مع طلب ETc مرتفع وميزانيّة مفتوحة.
    assert out["planned_total_mm"] == plan["total_irrigation_mm"]


def test_schedule_is_deterministic():
    fn = wd._HANDLERS["irrigation.real.schedule"]
    a = fn(_base_ctx())
    b = fn(_base_ctx())
    assert a["irrigation_plan"] == b["irrigation_plan"]


def test_schedule_respects_season_budget():
    fn = wd._HANDLERS["irrigation.real.schedule"]
    out = fn(_base_ctx(season_budget_mm=5.0))
    plan = out["irrigation_plan"]
    # الميزانيّة سقف صارم: الإجماليّ لا يتجاوزها.
    assert plan["total_irrigation_mm"] <= 5.0 + 1e-6


# ── execute: يحترم HITL، نيّة موسومة لا صمّام ─────────────────────────────


def test_execute_blocks_without_approval():
    sched = wd._HANDLERS["irrigation.real.schedule"](_base_ctx())
    ctx = _base_ctx(**sched)  # يضمّ irrigation_plan
    ctx["approval_status"] = "pending"
    out = wd._HANDLERS["irrigation.real.execute"](ctx)
    assert out["executed"] is False
    assert out["execution_intent"] is None
    assert out["_template"] is False


def test_execute_emits_logical_intent_when_approved():
    sched = wd._HANDLERS["irrigation.real.schedule"](_base_ctx())
    ctx = _base_ctx(**sched)
    ctx["approval_status"] = "approved"
    out = wd._HANDLERS["irrigation.real.execute"](ctx)
    if sched["planned_total_mm"] > 0:
        assert out["executed"] is True
        intent = out["execution_intent"]
        assert intent is not None
        assert intent["type"] == "irrigation_command_intent"
        # صدق: نيّة منطقيّة فقط — لم تُرسَل لعتاد (dispatched=False).
        assert intent["dispatched"] is False
        assert intent["field_id"] == "field-1"
    else:
        assert out["executed"] is False


def test_execute_no_water_no_intent():
    fn = wd._HANDLERS["irrigation.real.execute"]
    ctx = _base_ctx(approval_status="approved", irrigation_plan={"total_irrigation_mm": 0.0})
    out = fn(ctx)
    assert out["executed"] is False
    assert out["execution_intent"] is None


# ── verify: يقارن المُخطَّط بالمُنفَّذ ─────────────────────────────────────


def test_verify_matches_planned_executed():
    fn = wd._HANDLERS["irrigation.real.verify"]
    ctx = {
        "irrigation_plan": {"total_irrigation_mm": 30.0},
        "executed": True,
        "executed_total_mm": 30.0,
    }
    out = fn(ctx)
    assert out["verified"] is True
    assert out["match"] is True
    assert out["_template"] is False


def test_verify_detects_gap():
    fn = wd._HANDLERS["irrigation.real.verify"]
    ctx = {
        "irrigation_plan": {"total_irrigation_mm": 30.0},
        "executed": True,
        "executed_total_mm": 10.0,
    }
    out = fn(ctx)
    assert out["verified"] is False
    assert out["match"] is False
    assert out["delta_mm"] == pytest.approx(20.0)


def test_verify_reflects_no_execution():
    fn = wd._HANDLERS["irrigation.real.verify"]
    out = fn({"irrigation_plan": {"total_irrigation_mm": 30.0}, "executed": False})
    assert out["verified"] is False
    assert out["executed_mm"] == 0.0


# ── compensate: يبطل نيّة التنفيذ (Saga) ──────────────────────────────────


def test_compensate_cancels_intent():
    fn = wd._HANDLERS["irrigation.real.execute.compensate"]
    intent = {"type": "irrigation_command_intent", "dispatched": False}
    ctx = {"execution_intent": intent}
    out = fn(ctx)
    assert out["execution_cancelled"] is True
    assert intent["cancelled"] is True


# ── end-to-end عبر المحرّك مع العلم مُفعَّلاً (HITL: تعليق ثمّ استئناف) ─────


def test_real_workflow_suspends_then_resumes_with_approval(monkeypatch):
    monkeypatch.setenv("FEATURE_IRRIGATION_WORKFLOW_REAL", "1")
    # إعادة تحميل الوحدة لإعادة بناء التعريف خلف العلم المُفعَّل.
    import importlib

    from core.workflow_engine import InMemoryWorkflowStore, WorkflowStatus, run_workflow

    mod = importlib.reload(wd)
    try:
        defn = mod.get_workflow("irrigation_cycle")
        assert [s.step_name for s in defn.steps] == [
            "validate",
            "schedule",
            "approval_gate",
            "execute",
            "verify",
        ]
        steps = mod.build_steps(defn)
        store = InMemoryWorkflowStore()
        ctx = _base_ctx()  # لا approval_status ⇒ معلّق

        st1 = run_workflow("wf-irr-real", steps, store=store, tenant_id="t1", initial_context=ctx)
        # يصل لبوّابة الموافقة ويُعلَّق (HITL) — لم يُنفَّذ.
        assert st1.status == WorkflowStatus.SUSPENDED
        assert "execute" not in st1.completed_steps

        # موافقة الخبير عبر الاستئناف ⇒ يكمل execute → verify.
        st2 = run_workflow(
            "wf-irr-real",
            steps,
            store=store,
            tenant_id="t1",
            initial_context={"approval_status": "approved"},
        )
        assert st2.status == WorkflowStatus.COMPLETED
        assert "execute" in st2.completed_steps
        assert st2.step_results["execute"]["_template"] is False
    finally:
        # استعادة الوحدة بالعلم المُطفأ للحالة الافتراضيّة (عزل بين الاختبارات).
        monkeypatch.delenv("FEATURE_IRRIGATION_WORKFLOW_REAL", raising=False)
        importlib.reload(wd)


def test_flag_off_keeps_template_definition(monkeypatch):
    monkeypatch.delenv("FEATURE_IRRIGATION_WORKFLOW_REAL", raising=False)
    import importlib

    mod = importlib.reload(wd)
    try:
        flows = {f["id"]: f for f in mod.list_workflows()}
        assert flows["irrigation_cycle"]["step_names"] == [
            "validate",
            "schedule",
            "execute",
            "verify",
        ]
        # القالب يبقى pass-through موسوماً _template=True.
        out = mod._HANDLERS["irrigation.validate"]({})
        assert out == {"validated": True, "_template": True}
    finally:
        importlib.reload(wd)
