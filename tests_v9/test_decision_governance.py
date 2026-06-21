"""Unit tests: حَوكمة مسار القرار — منع تنفيذ قرار حوكمته not_evaluated.

يثبّت الخطّ الأحمر الذي أقرّته المراجعة: قرار من المسار القانونيّ
(field_intelligence_coordinator.run_field_intelligence) **لا يكون قابلاً
للتنفيذ/التوزيع** ما لم تمرّ القواعد الحاكمة فعليّاً وتُقرّ بحالة موافِقة.

نقيّ بلا قاعدة بيانات: نستخدم الدوالّ مباشرةً مع حقن مصادر/حواجز اختباريّة.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))


def _salinity_field_request():
    """طلب حقل + مصادر تنتج قراراً actionable (ملوحة حرجة)."""
    from core.field_intelligence_coordinator import FieldRequest

    req = FieldRequest(field_id="F-GOV-1", tenant_id="t-gov")

    def soil_fn(_req):
        # EC مرتفع جدّاً ⇒ effective_status=salinity_limited ⇒ decision.actionable=True
        return {"ec_dsm": 12.0, "sampled_at": "2026-06-01T00:00:00+00:00"}

    def sensing_fn(_req):
        return {"ndvi": 0.7, "field_coverage": 0.95}

    return req, soil_fn, sensing_fn


@pytest.mark.unit
def test_no_guardrails_means_not_evaluated_and_not_executable():
    """(أ) قرار بلا guardrails_fn: governance=not_evaluated و**غير قابل للتنفيذ**."""
    from core.field_intelligence_coordinator import run_field_intelligence

    req, soil_fn, sensing_fn = _salinity_field_request()
    result = run_field_intelligence(req, soil_fn=soil_fn, sensing_fn=sensing_fn)

    # القرار الزراعيّ فعلاً actionable (الملوحة حرجة) — لكنّ الحَوكمة لم تُقيَّم.
    assert result.policy_decision.get("actionable") is True
    assert result.governance.get("status") == "not_evaluated"
    # ENFORCEMENT: غياب الحَوكمة ⇒ غير قابل للتنفيذ، بسبب صريح، لا موافقة مختلقة.
    assert result.executable is False
    assert result.dispatch_block_reason == "governance_not_evaluated"
    assert result.policy_decision.get("executable") is False
    assert result.policy_decision.get("dispatch_block_reason") == "governance_not_evaluated"


@pytest.mark.unit
def test_approved_guardrails_makes_decision_executable():
    """(ب) قرار مع guardrails يُقرّ approved: قابل للتنفيذ."""
    from core.field_intelligence_coordinator import run_field_intelligence

    req, soil_fn, sensing_fn = _salinity_field_request()

    def guardrails_fn(_decision, _state):
        return {"status": "approved", "note": "مُخلَّص"}

    result = run_field_intelligence(
        req, soil_fn=soil_fn, sensing_fn=sensing_fn, guardrails_fn=guardrails_fn
    )

    assert result.policy_decision.get("actionable") is True
    assert result.governance.get("status") == "approved"
    assert result.executable is True
    assert result.dispatch_block_reason is None
    assert result.policy_decision.get("executable") is True


@pytest.mark.unit
def test_guardrails_error_blocks_execution():
    """قرار مع guardrails يفشل: governance=error ⇒ غير قابل للتنفيذ (fail-closed)."""
    from core.field_intelligence_coordinator import run_field_intelligence

    req, soil_fn, sensing_fn = _salinity_field_request()

    def guardrails_fn(_decision, _state):
        raise RuntimeError("guardrail backend down")

    result = run_field_intelligence(
        req, soil_fn=soil_fn, sensing_fn=sensing_fn, guardrails_fn=guardrails_fn
    )

    assert result.governance.get("status") == "error"
    assert result.executable is False
    assert result.dispatch_block_reason == "governance_error"


@pytest.mark.unit
def test_governance_permits_dispatch_helper():
    """مُساعِد البوّابة: لا يسمح إلّا بالحالات الموافِقة المعلومة (fail-closed)."""
    from core.field_intelligence_coordinator import governance_permits_dispatch

    assert governance_permits_dispatch({"status": "approved"}) is True
    assert governance_permits_dispatch({"status": "passed"}) is True
    assert governance_permits_dispatch({"status": "not_evaluated"}) is False
    assert governance_permits_dispatch({"status": "error"}) is False
    assert governance_permits_dispatch({}) is False
    assert governance_permits_dispatch(None) is False


@pytest.mark.unit
def test_dispatch_guard_refuses_not_evaluated_decision():
    """(ج) حارس بوّابة التوزيع يرفض قراراً not_evaluated (لا يصل evaluate_dispatch)."""
    from core.decision_dispatch import (
        GovernanceNotEvaluatedError,
        assert_governance_evaluated,
    )

    # not_evaluated ⇒ يُرفض بسبب صريح.
    with pytest.raises(GovernanceNotEvaluatedError) as exc:
        assert_governance_evaluated({"status": "not_evaluated"})
    assert "governance_not_evaluated" in str(exc.value)

    # حالة مجهولة/فارغة ⇒ تُرفض أيضاً (لا نُعامل المجهول كموافقة).
    with pytest.raises(GovernanceNotEvaluatedError):
        assert_governance_evaluated(None)
    with pytest.raises(GovernanceNotEvaluatedError):
        assert_governance_evaluated({"status": "error"})

    # approved ⇒ يمرّ بلا استثناء.
    assert assert_governance_evaluated({"status": "approved"}) is None
