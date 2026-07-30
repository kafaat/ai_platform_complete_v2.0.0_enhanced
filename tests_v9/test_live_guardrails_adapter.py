"""المحوّل الحيّ للحَوكمة (guardrails-engine /validate) — الأكثر حساسيّة للسلامة.

يثبّت أنّ القرار لا يصير `executable=True` إلّا إذا أقرّت guardrails فعليّاً
(allowed==True)؛ أيّ خلاف ذلك (رفض/خطأ/تعذّر/لا تناظر سلاميّ/توكن مفقود) يُبقيه
استشاريّاً (executable=False) — fail-closed، لا موافقة مختلقة.

نقيّ بلا شبكة: نرقّع `_post_json` (أو httpx.Client بـMockTransport) لمحاكاة /validate.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services", "sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)


def _salinity_field_request():
    """طلب حقل + مصادر تنتج قراراً actionable (ملوحة حرجة → soil_remediation)."""
    from core.field_intelligence_coordinator import FieldRequest

    req = FieldRequest(field_id="F-GR-1", tenant_id="t-gr")

    def soil_fn(_req):
        return {"ec_dsm": 12.0, "sampled_at": "2026-06-01T00:00:00+00:00"}

    def sensing_fn(_req):
        return {"ndvi": 0.7, "field_coverage": 0.95}

    return req, soil_fn, sensing_fn


def _advisory_trend_field_request():
    """طلب حقل ينتج قراراً actionable لكنّه استشاريّ/متابعة (لا action_type سلاميّ).

    اتّجاه NDVI هابط ⇒ decision.actionable=True بلا action_type (مجرّد «تابِع عن قرب»)
    ⇒ لا تناظر سلاميّ ⇒ guardrails_adapter يُرجِع not_applicable (يبقى استشاريّاً).
    """
    from core.field_intelligence_coordinator import FieldRequest

    req = FieldRequest(field_id="F-GR-2", tenant_id="t-gr")

    def sensing_fn(_req):
        return {"ndvi": 0.6, "field_coverage": 0.95}

    # تاريخ NDVI هابط ⇒ ndvi_trend=decreasing ⇒ actionable بلا action_type سلاميّ
    ndvi_history = [0.85, 0.78, 0.70, 0.62, 0.55]
    return req, sensing_fn, ndvi_history


# ── خريطة القرار → نوع إجراء guardrails (تعاقُد المصدر + السلوك النقيّ) ──


def test_mapping_salinity_to_irrigation():
    from core import field_intelligence_adapters as fia

    assert (
        fia._map_decision_to_guardrails_action(
            {"action_type": "soil_remediation", "structured": {"issue": "salinity"}}
        )
        == "irrigation"
    )


def test_mapping_investigate_stress_is_none():
    """investigate_stress تقييميّ بحت ⇒ لا تناظر سلاميّ ⇒ None (يُعامَل not_applicable)."""
    from core import field_intelligence_adapters as fia

    assert fia._map_decision_to_guardrails_action({"action_type": "investigate_stress"}) is None


def test_mapping_unknown_is_none_fail_closed():
    from core import field_intelligence_adapters as fia

    assert fia._map_decision_to_guardrails_action({"action_type": "totally_unknown"}) is None
    assert fia._map_decision_to_guardrails_action({}) is None


# ── سلوك guardrails_adapter المباشر (مع ترقيع _post_json) ──


def _state_with_truths():
    from datetime import UTC, datetime

    from core.agronomic_state_engine import CanonicalFieldState

    st = CanonicalFieldState(field_id="F-GR-1", generated_at=datetime.now(UTC).isoformat())
    st.tenant_id = "t-gr"
    st.operational_truths = {
        "effective_status": "salinity_limited",
        "salinity_class": "critical",
        "salinity_risk": 0.75,
    }
    return st


def test_adapter_approved_when_guardrails_allows(monkeypatch):
    from core import field_intelligence_adapters as fia

    monkeypatch.setattr(fia, "AGENT_TOKEN", "svc-token")
    monkeypatch.setattr(
        fia,
        "_post_json",
        lambda *a, **k: {"allowed": True, "overall_risk": "LOW", "tier_checks": []},
    )
    decision = {"action_type": "soil_remediation", "structured": {"issue": "salinity"}}
    gov = fia.guardrails_adapter(decision, _state_with_truths())
    assert gov["status"] == "approved"
    assert gov["overall_risk"] == "LOW"


def test_adapter_halted_when_guardrails_blocks(monkeypatch):
    from core import field_intelligence_adapters as fia

    monkeypatch.setattr(fia, "AGENT_TOKEN", "svc-token")
    monkeypatch.setattr(
        fia,
        "_post_json",
        lambda *a, **k: {"allowed": False, "overall_risk": "HIGH", "arabic_explanation": "مرفوض"},
    )
    decision = {"action_type": "soil_remediation", "structured": {"issue": "salinity"}}
    gov = fia.guardrails_adapter(decision, _state_with_truths())
    assert gov["status"] == "halted"  # NOT in GOVERNANCE_APPROVED_STATES


def test_adapter_error_when_unreachable(monkeypatch):
    from core import field_intelligence_adapters as fia

    monkeypatch.setattr(fia, "AGENT_TOKEN", "svc-token")
    monkeypatch.setattr(fia, "_post_json", lambda *a, **k: None)  # تعذّر/≠200
    decision = {"action_type": "soil_remediation", "structured": {"issue": "salinity"}}
    gov = fia.guardrails_adapter(decision, _state_with_truths())
    assert gov["status"] == "error"


def test_adapter_error_when_no_service_token(monkeypatch):
    from core import field_intelligence_adapters as fia

    monkeypatch.setattr(fia, "AGENT_TOKEN", "")  # توكن خدمة مفقود ⇒ fail-closed
    decision = {"action_type": "soil_remediation", "structured": {"issue": "salinity"}}
    gov = fia.guardrails_adapter(decision, _state_with_truths())
    assert gov["status"] == "error"


def test_adapter_not_applicable_for_advisory(monkeypatch):
    from core import field_intelligence_adapters as fia

    # حتى مع توكن، قرار تقييميّ بحت لا يُرسَل أصلاً ⇒ not_applicable (لا موافقة).
    monkeypatch.setattr(fia, "AGENT_TOKEN", "svc-token")

    def _fail(*a, **k):
        raise AssertionError("لا يجب استدعاء /validate لقرار استشاريّ")

    monkeypatch.setattr(fia, "_post_json", _fail)
    gov = fia.guardrails_adapter({"action_type": "investigate_stress"}, _state_with_truths())
    assert gov["status"] == "not_applicable"


def test_adapter_never_raises(monkeypatch):
    from core import field_intelligence_adapters as fia

    monkeypatch.setattr(fia, "AGENT_TOKEN", "svc-token")

    def _boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(fia, "_post_json", _boom)
    decision = {"action_type": "soil_remediation", "structured": {"issue": "salinity"}}
    gov = fia.guardrails_adapter(decision, _state_with_truths())  # لا يرفع
    assert gov["status"] == "error"


# ── التكامل end-to-end عبر run_field_intelligence ──


def test_e2e_approved_makes_executable(monkeypatch):
    """(أ) قرار ملوحة + guardrails allowed ⇒ governance approved ⇒ executable True."""
    from core import field_intelligence_adapters as fia
    from core.field_intelligence_coordinator import run_field_intelligence

    monkeypatch.setattr(fia, "AGENT_TOKEN", "svc-token")
    monkeypatch.setattr(fia, "_post_json", lambda *a, **k: {"allowed": True, "overall_risk": "LOW"})
    # DECISION-CENTER-UNIFY-01: escape flag to test the legacy guardrails->executable gate.
    monkeypatch.setenv("FIELD_INTELLIGENCE_DIRECT_EXECUTABLE_ENABLED", "1")

    req, soil_fn, sensing_fn = _salinity_field_request()

    def guardrails_fn(decision, state):
        return fia.guardrails_adapter(decision, state)

    result = run_field_intelligence(
        req, soil_fn=soil_fn, sensing_fn=sensing_fn, guardrails_fn=guardrails_fn
    )
    assert result.policy_decision.get("actionable") is True
    assert result.governance.get("status") == "approved"
    assert result.executable is True
    assert result.dispatch_block_reason is None


def test_e2e_blocked_stays_advisory(monkeypatch):
    """(ب) guardrails allowed=False ⇒ halted ⇒ executable False."""
    from core import field_intelligence_adapters as fia
    from core.field_intelligence_coordinator import run_field_intelligence

    monkeypatch.setattr(fia, "AGENT_TOKEN", "svc-token")
    monkeypatch.setattr(
        fia, "_post_json", lambda *a, **k: {"allowed": False, "overall_risk": "CRITICAL"}
    )

    req, soil_fn, sensing_fn = _salinity_field_request()
    result = run_field_intelligence(
        req,
        soil_fn=soil_fn,
        sensing_fn=sensing_fn,
        guardrails_fn=lambda d, s: fia.guardrails_adapter(d, s),
    )
    assert result.governance.get("status") == "halted"
    assert result.executable is False


def test_e2e_error_stays_advisory(monkeypatch):
    """(ج) guardrails تعذّر ⇒ error ⇒ executable False."""
    from core import field_intelligence_adapters as fia
    from core.field_intelligence_coordinator import run_field_intelligence

    monkeypatch.setattr(fia, "AGENT_TOKEN", "svc-token")
    monkeypatch.setattr(fia, "_post_json", lambda *a, **k: None)

    req, soil_fn, sensing_fn = _salinity_field_request()
    result = run_field_intelligence(
        req,
        soil_fn=soil_fn,
        sensing_fn=sensing_fn,
        guardrails_fn=lambda d, s: fia.guardrails_adapter(d, s),
    )
    assert result.governance.get("status") == "error"
    assert result.executable is False
    assert result.dispatch_block_reason == "governance_error"


def test_e2e_advisory_decision_not_applicable(monkeypatch):
    """(د) قرار تقييميّ (investigate_stress) ⇒ not_applicable ⇒ executable False."""
    from core import field_intelligence_adapters as fia
    from core.field_intelligence_coordinator import run_field_intelligence

    monkeypatch.setattr(fia, "AGENT_TOKEN", "svc-token")

    def _fail(*a, **k):
        raise AssertionError("لا /validate لقرار تقييميّ")

    monkeypatch.setattr(fia, "_post_json", _fail)

    req, sensing_fn, ndvi_history = _advisory_trend_field_request()
    result = run_field_intelligence(
        req,
        sensing_fn=sensing_fn,
        ndvi_history=ndvi_history,
        guardrails_fn=lambda d, s: fia.guardrails_adapter(d, s),
    )
    # actionable لكن بلا action_type سلاميّ (مجرّد متابعة) ⇒ not_applicable ⇒ غير قابل للتنفيذ.
    assert result.policy_decision.get("actionable") is True
    assert result.policy_decision.get("action_type") is None
    assert result.governance.get("status") == "not_applicable"
    assert result.executable is False


# ── (هـ) تعاقُد: X-Agent-Token يُرسَل فعليّاً على نداء /validate ──


@pytest.mark.skipif(
    importlib.util.find_spec("httpx") is None, reason="httpx غير متاح في بيئة الوحدات الخفيفة"
)
def test_validate_sends_agent_token_header(monkeypatch):
    """سلوكيّ: guardrails_adapter يُرسل X-Agent-Token لـ/validate (transport وهميّ)."""
    import httpx
    from core import field_intelligence_adapters as fia

    monkeypatch.setattr(fia, "AGENT_TOKEN", "secret-svc-token")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["X-Agent-Token"] = request.headers.get("X-Agent-Token")
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"allowed": True, "overall_risk": "LOW"})

    real_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda *a, **k: real_client(transport=httpx.MockTransport(handler))
    )
    decision = {"action_type": "soil_remediation", "structured": {"issue": "salinity"}}
    gov = fia.guardrails_adapter(decision, _state_with_truths())
    assert gov["status"] == "approved"
    assert captured["X-Agent-Token"] == "secret-svc-token"
    assert captured["url"].endswith("/v1/validate")


# ── الراية: التعطيل يُخفي guardrails_fn (رجوع آمن للاستشاريّ) ──


def test_env_gate_disabled_omits_guardrails_fn(monkeypatch):
    """ENABLE_LIVE_GUARDRAILS=false ⇒ build_live_adapters لا يضيف guardrails_fn."""
    import importlib

    monkeypatch.setenv("ENABLE_LIVE_GUARDRAILS", "false")
    from core import field_intelligence_adapters as fia

    importlib.reload(fia)
    try:
        adapters = fia.build_live_adapters(authorization="Bearer x")
        assert "guardrails_fn" not in adapters
    finally:
        monkeypatch.setenv("ENABLE_LIVE_GUARDRAILS", "true")
        importlib.reload(fia)


def test_env_gate_default_includes_guardrails_fn():
    """افتراضيّاً (DEFAULT ON) ⇒ guardrails_fn موجود في المحوّلات الحيّة."""
    from core import field_intelligence_adapters as fia

    adapters = fia.build_live_adapters(authorization="Bearer x")
    assert "guardrails_fn" in adapters
    assert callable(adapters["guardrails_fn"])
