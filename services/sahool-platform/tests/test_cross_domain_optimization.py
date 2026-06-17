"""اختبارات الأمثَلة متعدّدة الأهداف للريّ (core.cross_domain_optimization) — المرحلة B، 7.

نقيّة وحتميّة ⇒ `unit`. تثبّت: الكمّيّة المثلى توازن كفاءة الماء وأمان الغلّة عند الحدّ
الأدنى، احترام الميزانيّة، حالات الحدود (مطلوب صفر، حدّ غلّة فوق المتاح)، والأوزان.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from core.cross_domain_optimization import _clamp01, optimize_irrigation  # noqa: E402


# ── تقوية بالطفرات: _clamp01 (تُستعمَل لكلّ درجات الأهداف) — قيم دقيقة تقتل الطفرات ──
def test_clamp01_exact_values():
    assert _clamp01(-5.0) == 0.0  # دون الصفر ⇒ 0
    assert _clamp01(0.0) == 0.0
    assert _clamp01(0.37) == 0.37  # داخل [0,1] ⇒ كما هو
    assert _clamp01(1.0) == 1.0  # الحدّ ⇒ 1
    assert _clamp01(2.5) == 1.0  # فوق 1 ⇒ 1 (يقتل const 1.0→False)
    # القيم منطقيّة-عدديّة صارمة (1.0 لا True، 0.0 لا False)
    assert _clamp01(2.5) is not True and _clamp01(-1.0) is not False


# ── تقوية بالطفرات: قيم ذهبيّة دقيقة للمخرج (تقتل طفرات الحساب في الحلقة) ──
def test_exact_optimum_balanced():
    # مطلوب 20، حدّ غلّة 10، أوزان متساوية، 10 خطوات ⇒ الأمثل عند الحدّ تماماً = 10.0
    r = optimize_irrigation(20.0, min_mm_for_yield=10.0, steps=10)
    assert r.applied_water_mm == 10.0  # دقيق لا تقريبيّ
    assert r.water_saved_mm == 10.0
    assert r.objective_scores == {"water_efficiency": 0.5, "yield_security": 1.0}
    assert r.candidates_evaluated == 11  # steps+1 بالضبط (يقتل طفرة Add→Sub / const)


def test_exact_budget_cap_value():
    # ميزانيّة 8 < مطلوب 20؛ حدّ غلّة 18 فوق المتاح ⇒ يختار الأعلى المتاح = 8.0 بالضبط
    r = optimize_irrigation(20.0, min_mm_for_yield=18.0, budget_mm=8.0, steps=8)
    assert r.applied_water_mm == 8.0
    assert r.requested_water_mm == 20.0
    assert r.water_saved_mm == 12.0


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
