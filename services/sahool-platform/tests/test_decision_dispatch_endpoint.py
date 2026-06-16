"""اختبارات نقطة معاينة قرار التوزيع (routers/decision_dispatch) — استدعاء مباشر.

نختبر المعالِج مباشرةً (دالّة نقيّة: علم → check_guardrails → evaluate_dispatch)،
متفادين TestClient/المصادقة: العلم المُطفأ ⇒ 404؛ المُفعَّل ⇒ قرار صحيح (HALT يحجب،
الموافقة تُخلّص)، مع أثر dry_run/evaluated_by. لا تنفيذ، لا قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main كاملةً قبل استيراد الموجِّه (تفادي دورة استيراد)
import pytest
from api.routers.decision_dispatch import (
    DispatchEvaluateRequest,
    evaluate_dispatch_endpoint,
)
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-eval",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="مُعايِن",
)


def _req(**kw):
    base = dict(recommendation_id="rec1", action_type="irrigation", risk_level="LOW")
    base.update(kw)
    return DispatchEvaluateRequest(**base)


def test_flag_off_returns_404(monkeypatch):
    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    with pytest.raises(HTTPException) as e:
        evaluate_dispatch_endpoint(req=_req(), user=_USER)
    assert e.value.status_code == 404


def test_flag_on_low_risk_ready(monkeypatch):
    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "true")
    out = evaluate_dispatch_endpoint(req=_req(risk_level="LOW"), user=_USER)
    assert out["state"] == "ready"
    assert out["executable"] is True
    assert out["dry_run"] is True
    assert out["evaluated_by"] == "u-eval"


def test_flag_on_pesticide_phi_blocks(monkeypatch):
    # PHI غير مُستوفى ⇒ خرق HALT ⇒ BLOCKED مهما كانت الموافقات.
    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "1")
    out = evaluate_dispatch_endpoint(
        req=_req(risk_level="LOW", pesticide_phi_satisfied=False, approvals_collected=99),
        user=_USER,
    )
    assert out["state"] == "blocked"
    assert out["executable"] is False
    assert "pesticide_phi" in out["halt_breaches"]


def test_flag_on_medium_pending_then_ready(monkeypatch):
    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "yes")
    pending = evaluate_dispatch_endpoint(
        req=_req(action_type="fertilize", risk_level="MEDIUM", approvals_collected=0), user=_USER
    )
    assert pending["state"] == "pending_approval"
    ready = evaluate_dispatch_endpoint(
        req=_req(action_type="fertilize", risk_level="MEDIUM", approvals_collected=1), user=_USER
    )
    assert ready["state"] == "ready"


def test_flag_on_salinity_halt_via_guardrails(monkeypatch):
    # ملوحة تتجاوز عتبة المحصول بشدّة ⇒ HALT من check_guardrails ⇒ BLOCKED.
    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "on")
    out = evaluate_dispatch_endpoint(
        req=_req(risk_level="HIGH", soil_ec_ds_m=12.0, crop_salinity_threshold_ds_m=4.0),
        user=_USER,
    )
    assert out["state"] == "blocked"
    assert any("salinity" in b for b in out["halt_breaches"])
