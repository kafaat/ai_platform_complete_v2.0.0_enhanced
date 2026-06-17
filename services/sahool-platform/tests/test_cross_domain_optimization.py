"""اختبارات الأمثَلة متعدّدة الأهداف للريّ (core.cross_domain_optimization) — المرحلة B، 7.

نقيّة وحتميّة ⇒ `unit`. تثبّت: الكمّيّة المثلى توازن كفاءة الماء وأمان الغلّة عند الحدّ
الأدنى، احترام الميزانيّة، حالات الحدود (مطلوب صفر، حدّ غلّة فوق المتاح)، والأوزان.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from core.cross_domain_optimization import optimize_irrigation  # noqa: E402


def test_optimum_at_yield_minimum_when_equal_weights():
    # بأوزان متساوية: الأمثل = الحدّ الأدنى للغلّة (يؤمّن الغلّة ويوفّر الباقي).
    r = optimize_irrigation(20.0, min_mm_for_yield=12.0, steps=20)
    assert r.applied_water_mm == pytest.approx(12.0, abs=1.0)
    assert r.water_saved_mm > 0
    assert r.objective_scores["yield_security"] == pytest.approx(1.0, abs=0.05)
    assert any("حدّ الغلّة" in t for t in r.tradeoffs_ar)


def test_budget_caps_applied_water():
    r = optimize_irrigation(20.0, min_mm_for_yield=18.0, budget_mm=10.0, steps=10)
    assert r.applied_water_mm <= 10.0
    assert any("الميزانيّة" in t for t in r.tradeoffs_ar)


def test_yield_at_risk_when_min_above_budget():
    r = optimize_irrigation(20.0, min_mm_for_yield=15.0, budget_mm=10.0, steps=10)
    # الحدّ الأدنى للغلّة (15) فوق المتاح (10) ⇒ خطر معلَن، يختار الأعلى المتاح.
    assert any("خطر على الغلّة" in t for t in r.tradeoffs_ar)
    assert r.applied_water_mm == pytest.approx(10.0, abs=1.0)


def test_zero_request_no_irrigation():
    r = optimize_irrigation(0.0, min_mm_for_yield=10.0)
    assert r.applied_water_mm == 0.0
    assert r.score == 1.0
    assert r.candidates_evaluated == 0


def test_water_efficiency_weight_favors_saving():
    # وزن كفاءة الماء العالي ⇒ كمّيّة أقلّ (يضحّي بأمان الغلّة لتوفير الماء).
    high_eff = optimize_irrigation(
        20.0,
        min_mm_for_yield=12.0,
        weights={"water_efficiency": 0.9, "yield_security": 0.1},
        steps=20,
    )
    balanced = optimize_irrigation(20.0, min_mm_for_yield=12.0, steps=20)
    assert high_eff.applied_water_mm <= balanced.applied_water_mm


def test_yield_weight_favors_security():
    high_yield = optimize_irrigation(
        20.0,
        min_mm_for_yield=18.0,
        weights={"water_efficiency": 0.1, "yield_security": 0.9},
        steps=20,
    )
    assert high_yield.applied_water_mm == pytest.approx(18.0, abs=1.0)


def test_no_min_yield_maximizes_efficiency():
    # حدّ غلّة = 0 ⇒ أمان الغلّة دائماً 1 ⇒ كفاءة الماء تقود ⇒ أقلّ ماء.
    r = optimize_irrigation(20.0, min_mm_for_yield=0.0, steps=10)
    assert r.applied_water_mm == 0.0


def test_result_serializable():
    import json

    r = optimize_irrigation(20.0, min_mm_for_yield=12.0)
    blob = json.dumps(r.to_dict(), ensure_ascii=False)
    parsed = json.loads(blob)
    assert parsed["water_saved_mm"] == r.water_saved_mm
    assert "objective_scores" in parsed
