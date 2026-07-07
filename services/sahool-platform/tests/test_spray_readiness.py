"""تحقّق — قرار «هل أرشّ الآن؟» (go/no-go) يوحّد الطقس + الانجراف (منطق صرف).

- أسوأ العاملَين يحكم؛ الانجراف الفعليّ حاجب مطلق (no_go).
- مدخلان مجهولان ⇒ unknown (لا قرار بلا أساس).
- انجراف unknown لا يرفع الشدّة (لا حجب بلا دليل).
"""

from __future__ import annotations

from core.spray_readiness import spray_go_no_go


def _weather(suit):
    return {"suitability": suit, "score": 0.9, "limiting_factors": []}


def _drift(status, n=0):
    return {"status": status, "exposed_zones": [{"id": f"z{i}"} for i in range(n)]}


def test_go_when_weather_ok_and_no_drift():
    out = spray_go_no_go(_weather("optimal"), _drift("clear"))
    assert out["decision"] == "go" and out["reasons"]


def test_drift_at_risk_is_hard_no_go_even_if_weather_optimal():
    out = spray_go_no_go(_weather("optimal"), _drift("at_risk", n=2))
    assert out["decision"] == "no_go"
    assert any("انجراف" in r for r in out["reasons"])


def test_worst_factor_governs_weather_unsafe():
    assert spray_go_no_go(_weather("unsafe"), _drift("clear"))["decision"] == "no_go"
    assert spray_go_no_go(_weather("poor"), _drift("clear"))["decision"] == "caution"


def test_unknown_when_no_inputs():
    out = spray_go_no_go(None, None)
    assert out["decision"] == "unknown" and out["reason"] == "no_inputs"
    # طقس فقط ⇒ يُستعمَل؛ انجراف مجهول لا يرفع الشدّة.
    assert spray_go_no_go(_weather("optimal"), _drift("unknown"))["decision"] == "go"


def test_drift_unknown_does_not_block():
    # صدق: لا نحجب بلا دليل انجراف — الطقس وحده يقرّر.
    out = spray_go_no_go(_weather("poor"), {"status": "unknown"})
    assert out["decision"] == "caution" and out["drift_status"] == "unknown"
