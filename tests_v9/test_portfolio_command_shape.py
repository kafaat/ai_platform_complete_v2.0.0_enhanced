"""اختبارات نقيّة لمركز قيادة المحفظة (api.portfolio_command).

منطق صرف بلا قاعدة: مقارنة سياسات على الربح×المخاطر تحت قيود البئر/المضخّة/المحور،
ترشيح الأفضل **كتوصية فقط**، وصدق المدخلات (لا تلفيق، calibrated=False).
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.portfolio_allocation import PortfolioField  # noqa: E402
from api.portfolio_command import (  # noqa: E402
    ConstraintSource,
    PolicyScenario,
    _effective_capacity,
    _risk_score,
    compare_portfolio_policies,
    evaluate_policy_scenario,
)


def _field(fid, margin, demand, **kw):
    return PortfolioField(field_id=fid, expected_margin=margin, water_demand_m3=demand, **kw)


def test_pump_throughput_binds_below_capacity():
    # مضخّة: سعة 1000 لكن تدفّق 100/يوم × 5 أيّام = 500 < 1000 ⇒ السعة الفعّالة 500 مُلزِمة.
    cap, bound = _effective_capacity(
        ConstraintSource("p1", capacity_m3=1000, kind="pump", max_rate_m3_per_day=100, window_days=5)
    )
    assert cap == 500
    assert bound is True


def test_well_capacity_not_bound_without_rate():
    # بئر بلا حدّ تدفّق ⇒ السعة الكلّيّة كما هي، غير مُلزَمة.
    cap, bound = _effective_capacity(ConstraintSource("w1", capacity_m3=800, kind="well"))
    assert cap == 800
    assert bound is False


def test_risk_score_bounds_and_weighting():
    # لا مخاطر ⇒ 0؛ كلّ الحقول بلا ريّ ⇒ يقترب من الأعلى (وزن unmet=0.5 + ماء غير مموّل=0.2).
    assert _risk_score(4, 0, 0, 0.0) == 0.0
    high = _risk_score(2, 2, 0, 1.0)
    assert high == round(0.5 + 0.2, 3)  # 0.7
    assert 0.0 <= high <= 1.0


def test_evaluate_policy_overlays_profit_and_risk():
    # سعة كافية ⇒ ربح كامل، مخاطر صفر، لا قيد مُلزِم.
    out = evaluate_policy_scenario(
        [_field("f1", 100, 50), _field("f2", 80, 50)],
        [ConstraintSource("w1", capacity_m3=200, kind="well")],
        policy_label="profit_max",
    )
    assert out["policy"] == "profit_max"
    assert out["total_expected_margin"] == 180.0
    assert out["unmet_count"] == 0
    assert out["risk_score"] == 0.0
    assert out["served_fraction"] == 1.0
    assert out["constraints_bound"] == []


def test_scarcity_raises_risk_and_unmet():
    # ماء شحيح ⇒ حقل غير مموّل ⇒ مخاطر > 0 + unmet_count يُعلَن (صدق: لا تلفيق).
    out = evaluate_policy_scenario(
        [_field("f1", 100, 100, priority=2), _field("f2", 50, 100, priority=1)],
        [ConstraintSource("w1", capacity_m3=100, kind="well")],
        policy_label="water_saving",
    )
    assert out["risk_score"] > 0.0
    assert out["served_fraction"] < 1.0
    assert out["unmet_count"] >= 1


def test_compare_recommends_best_objective_and_is_advice_only():
    # سياستان: A ربح أعلى مع مخاطر، B ربح أقلّ بلا مخاطر. النُّفور العالي يُرجّح B.
    plenty = [ConstraintSource("w", capacity_m3=1000, kind="well")]
    scarce = [ConstraintSource("w", capacity_m3=60, kind="well")]
    scenarios = [
        PolicyScenario("profit_max", [_field("f1", 200, 100), _field("f2", 50, 100)], scarce),
        PolicyScenario("risk_averse", [_field("f1", 90, 50), _field("f2", 90, 50)], plenty),
    ]
    out = compare_portfolio_policies(scenarios, risk_aversion=2.0)
    assert out["recommended_policy"] == "risk_averse"
    assert out["calibrated"] is False
    # توصية فقط: التحذيرات تنصّ صراحةً على لا تنفيذ.
    assert any("توصية فقط" in w for w in out["warnings_ar"])


def test_risk_aversion_zero_is_pure_margin():
    # نُفور = 0 ⇒ الهدف ربح صرف ⇒ يُرجّح أعلى ربح ولو بمخاطر.
    scenarios = [
        PolicyScenario(
            "profit_max",
            [_field("f1", 300, 100), _field("f2", 50, 100)],
            [ConstraintSource("w", capacity_m3=120, kind="well")],  # شحّ ⇒ مخاطر
        ),
        PolicyScenario(
            "safe",
            [_field("f1", 100, 50)],
            [ConstraintSource("w", capacity_m3=1000, kind="well")],
        ),
    ]
    out = compare_portfolio_policies(scenarios, risk_aversion=0.0)
    # profit_max يحقّق ربحاً أعلى رغم المخاطر ⇒ يُرشَّح عند نُفور صفر.
    assert out["recommended_policy"] == "profit_max"
    assert out["risk_aversion"] == 0.0


def test_bound_sources_surface_in_warnings():
    # مضخّة قيَّدها تدفّقها ⇒ تظهر في constraints_bound وفي تحذير صريح.
    scenarios = [
        PolicyScenario(
            "p",
            [_field("f1", 100, 1000)],
            [ConstraintSource("pump1", capacity_m3=1000, kind="pump", max_rate_m3_per_day=50, window_days=4)],
        )
    ]
    out = compare_portfolio_policies(scenarios)
    assert out["policies"][0]["constraints_bound"] == ["pump1"]
    assert any("pump1" in w for w in out["warnings_ar"])


def test_empty_scenarios_safe():
    # لا سيناريوهات ⇒ لا ترشيح، لا انهيار.
    out = compare_portfolio_policies([])
    assert out["recommended_policy"] is None
    assert out["policies"] == []
    assert out["calibrated"] is False
