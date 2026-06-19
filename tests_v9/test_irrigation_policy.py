"""اختبار طبقة سياسة الريّ + مُحلِّل السياق (#375) — نقيّ حتميّ.

يثبت: (أ) مقابض السياسات الخمس؛ (ب) توافق "profit"⇒profit_max؛ (ج) PROFIT_MAX بلا
أسعار ⇒ تراجع water_saving؛ (د) بأسعار ⇒ refill [0.7,1.0]؛ (هـ) سياسة مجهولة ⇒ تراجع؛
(و) المُحلِّل: بئر عميق/ماء غالٍ ⇒ PROFIT_MAX، ماء رخيص+سطحيّ ⇒ YIELD_MAX، الافتراضيّ
WATER_SAVING؛ (ز) أمثلة المستخدم (قمح+ماء رخيص، حمضيات+بئر عميق). نواة بلا شبكة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.irrigation_policy import (  # noqa: E402
    IrrigationPolicy,
    PolicyContext,
    policy_params,
    resolve_policy,
)


def test_water_saving_knobs():
    pp = policy_params(IrrigationPolicy.WATER_SAVING)
    assert pp.trigger_fraction == 1.0
    assert pp.refill_fraction == 0.80
    assert pp.allow_stress is True


def test_yield_max_knobs():
    pp = policy_params(IrrigationPolicy.YIELD_MAX)
    assert pp.trigger_fraction == 0.90
    assert pp.refill_fraction == 1.00
    assert pp.allow_stress is False


def test_sustainability_leaves_storage():
    pp = policy_params(IrrigationPolicy.SUSTAINABILITY)
    # ملء أقلّ ⇒ سعة تخزين للمطر ⇒ تسرّب عميق أقلّ.
    assert pp.refill_fraction == 0.75
    assert pp.allow_stress is True


def test_risk_averse_triggers_early_full_refill():
    pp = policy_params(IrrigationPolicy.RISK_AVERSE)
    assert pp.trigger_fraction == 0.80  # مبكّر (هامش أمان)
    assert pp.refill_fraction == 1.00
    assert pp.allow_stress is False


def test_profit_alias_accepted():
    assert policy_params("profit", 0.05, 2000.0).policy is IrrigationPolicy.PROFIT_MAX


def test_profit_without_prices_falls_back():
    pp = policy_params(IrrigationPolicy.PROFIT_MAX)
    assert pp.policy is IrrigationPolicy.WATER_SAVING
    assert any("PROFIT_MAX يتطلّب" in n for n in pp.notes_ar)


def test_profit_with_prices_active_and_bounded():
    pp = policy_params(
        IrrigationPolicy.PROFIT_MAX, water_price_per_m3=0.05, yield_value_per_ha=2000.0
    )
    assert pp.policy is IrrigationPolicy.PROFIT_MAX
    assert 0.7 <= pp.refill_fraction <= 1.0
    assert any("heuristic" in n for n in pp.notes_ar)


def test_expensive_water_reduces_refill():
    cheap = policy_params(
        IrrigationPolicy.PROFIT_MAX, water_price_per_m3=0.01, yield_value_per_ha=5000.0
    )
    dear = policy_params(
        IrrigationPolicy.PROFIT_MAX, water_price_per_m3=0.10, yield_value_per_ha=2000.0
    )
    assert dear.refill_fraction <= cheap.refill_fraction


def test_unknown_policy_falls_back():
    pp = policy_params("nonsense")
    assert pp.policy is IrrigationPolicy.WATER_SAVING
    assert any("غير معروفة" in n for n in pp.notes_ar)


def test_calibrated_false():
    assert policy_params(IrrigationPolicy.WATER_SAVING).calibrated is False


# ── مُحلِّل السياق ──────────────────────────────────────────────────────────


def test_resolver_deep_well_expensive_picks_profit():
    # مثال المستخدم: حمضيات + بئر عميق + ضخّ غالٍ ⇒ PROFIT_MAX.
    pol, reasons = resolve_policy(
        PolicyContext(crop="citrus", water_source="deep_well", energy_cost="expensive")
    )
    assert pol is IrrigationPolicy.PROFIT_MAX
    assert any("PROFIT_MAX" in r for r in reasons)


def test_resolver_cheap_water_surface_picks_yield_max():
    # مثال المستخدم: قمح محوريّ + ماء رخيص ⇒ YIELD_MAX.
    pol, reasons = resolve_policy(
        PolicyContext(crop="wheat", water_source="surface", water_cost="cheap")
    )
    assert pol is IrrigationPolicy.YIELD_MAX


def test_resolver_aquifer_stressed_picks_sustainability():
    pol, _ = resolve_policy(PolicyContext(region="aquifer_stressed"))
    assert pol is IrrigationPolicy.SUSTAINABILITY


def test_resolver_default_is_water_saving():
    pol, reasons = resolve_policy(PolicyContext())
    assert pol is IrrigationPolicy.WATER_SAVING
    assert any("الأحوط" in r for r in reasons)


def test_resolver_output_feeds_policy_params():
    pol, _ = resolve_policy(PolicyContext(water_source="surface", water_cost="cheap"))
    pp = policy_params(pol)
    assert pp.policy is IrrigationPolicy.YIELD_MAX
