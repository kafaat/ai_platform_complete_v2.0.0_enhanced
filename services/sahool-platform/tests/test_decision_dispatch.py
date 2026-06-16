"""اختبارات موزِّع القرار المحروس (core.decision_dispatch) — نقيّ offline.

يتحقّق من دماغ الحلقة المغلقة: HALT ⇒ BLOCKED قطعاً (لا يتجاوزه بشر)، طبقات الموافقة
(LOW=0/MEDIUM=1/HIGH=2/CRITICAL=3 مطابِقة لـhuman_in_loop)، المستوى المجهول fail-closed،
وأثر التدقيق الموحّد. يستعمل أنواع الحواجز الحقيقيّة (core.guardrails) لا وهميّة.
"""

import pytest
from core.decision_dispatch import (
    DispatchState,
    evaluate_dispatch,
    required_approvals_for,
)
from core.guardrails import GuardrailBreach, GuardrailResult, GuardrailSeverity

pytestmark = pytest.mark.unit


def _gr(*breaches: GuardrailBreach) -> GuardrailResult:
    return GuardrailResult(
        passed=not any(b.severity == GuardrailSeverity.HALT for b in breaches),
        breaches=list(breaches),
    )


def _halt(name="pesticide_phi"):
    return GuardrailBreach(name, GuardrailSeverity.HALT, "خط أحمر")


def _warn(name="salinity_high"):
    return GuardrailBreach(name, GuardrailSeverity.WARN, "تحذير")


# ── طبقات الموافقة ──────────────────────────────────────────────
def test_required_approvals_tiers_match_human_in_loop():
    assert required_approvals_for("LOW") == 0
    assert required_approvals_for("MEDIUM") == 1
    assert required_approvals_for("HIGH") == 2
    assert required_approvals_for("CRITICAL") == 3


def test_unknown_risk_is_conservative_critical():
    # fail-closed: مستوى مجهول يتطلّب أعلى تحفّظ (لا يُخلَّص بسهولة).
    assert required_approvals_for("غير-معروف") == 3
    assert required_approvals_for("") == 3
    assert required_approvals_for(None) == 3  # type: ignore[arg-type]


# ── HALT يحجب قطعاً ─────────────────────────────────────────────
def test_halt_blocks_regardless_of_approvals():
    # الخط الأحمر لا يُتجاوَز حتى بموافقات وافرة.
    d = evaluate_dispatch(
        recommendation_id="rec1",
        action_type="irrigation",
        risk_level="LOW",
        guardrail=_gr(_halt("pesticide_phi")),
        approvals_collected=99,
    )
    assert d.state == DispatchState.BLOCKED
    assert d.executable is False
    assert d.halt_breaches == ["pesticide_phi"]
    assert "pesticide_phi" in d.reason_ar


def test_halt_takes_precedence_over_warn():
    d = evaluate_dispatch(
        recommendation_id="r",
        action_type="spraying",
        risk_level="HIGH",
        guardrail=_gr(_warn("salinity_high"), _halt("governing_data")),
        approvals_collected=5,
    )
    assert d.state == DispatchState.BLOCKED
    assert "governing_data" in d.halt_breaches
    assert "salinity_high" in d.warn_breaches  # التحذير يُسجَّل رغم الحجب


# ── بوّابة الموافقة ─────────────────────────────────────────────
def test_low_risk_ready_without_approval():
    d = evaluate_dispatch(
        recommendation_id="r", action_type="note", risk_level="LOW", guardrail=_gr()
    )
    assert d.state == DispatchState.READY
    assert d.executable is True
    assert d.required_approvals == 0


def test_medium_risk_pending_until_one_approval():
    base = dict(
        recommendation_id="r", action_type="fertilize", risk_level="MEDIUM", guardrail=_gr()
    )
    assert evaluate_dispatch(**base, approvals_collected=0).state == DispatchState.PENDING_APPROVAL
    ready = evaluate_dispatch(**base, approvals_collected=1)
    assert ready.state == DispatchState.READY and ready.executable is True


def test_critical_needs_three_approvals():
    base = dict(
        recommendation_id="r", action_type="irrigation", risk_level="CRITICAL", guardrail=_gr()
    )
    assert evaluate_dispatch(**base, approvals_collected=2).state == DispatchState.PENDING_APPROVAL
    assert evaluate_dispatch(**base, approvals_collected=3).state == DispatchState.READY


def test_warn_does_not_block_ready_path():
    # التحذيرات لا تحجب — تُرفَق فقط.
    d = evaluate_dispatch(
        recommendation_id="r",
        action_type="irrigation",
        risk_level="LOW",
        guardrail=_gr(_warn("salinity_high")),
    )
    assert d.state == DispatchState.READY
    assert d.warn_breaches == ["salinity_high"]
    assert "salinity_high" in d.reason_ar


def test_negative_approvals_clamped():
    d = evaluate_dispatch(
        recommendation_id="r",
        action_type="x",
        risk_level="MEDIUM",
        guardrail=_gr(),
        approvals_collected=-5,
    )
    assert d.approvals_collected == 0
    assert d.state == DispatchState.PENDING_APPROVAL


# ── أثر التدقيق الموحّد ─────────────────────────────────────────
def test_audit_trail_links_recommendation_to_decision():
    d = evaluate_dispatch(
        recommendation_id="rec-42",
        action_type="irrigation",
        risk_level="HIGH",
        guardrail=_gr(_warn("salinity_high")),
        field_id="fld_abc",
        approvals_collected=2,
    )
    audit = d.to_audit()
    assert audit["recommendation_id"] == "rec-42"
    assert audit["field_id"] == "fld_abc"
    assert audit["state"] == "ready"
    assert audit["executable"] is True
    assert audit["required_approvals"] == 2
    assert audit["warn_breaches"] == ["salinity_high"]
    # قابل للتسلسل (JSONB للسجلّ)
    import json

    assert json.dumps(audit, ensure_ascii=False)


def test_only_ready_is_executable():
    # العقد الأمنيّ: الشريحة اللاحقة تُنفّذ READY فقط — BLOCKED/PENDING غير قابلَين.
    for risk, appr, expected in [
        ("LOW", 0, True),
        ("MEDIUM", 0, False),
        ("CRITICAL", 3, True),
    ]:
        d = evaluate_dispatch(
            recommendation_id="r",
            action_type="x",
            risk_level=risk,
            guardrail=_gr(),
            approvals_collected=appr,
        )
        assert d.executable is expected
    blocked = evaluate_dispatch(
        recommendation_id="r", action_type="x", risk_level="LOW", guardrail=_gr(_halt())
    )
    assert blocked.executable is False
