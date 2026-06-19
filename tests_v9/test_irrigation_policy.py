"""اختبار طبقة سياسة الريّ (#375) — نقيّ حتميّ.

يثبت: (أ) مقابض WATER_SAVING/YIELD_MAX؛ (ب) PROFIT بلا أسعار ⇒ تراجع water_saving
+ تحذير؛ (ج) PROFIT بأسعار ⇒ refill في [0.7,1.0] + علم؛ (د) سياسة مجهولة ⇒ تراجع؛
(هـ) calibrated=False. نواة بلا شبكة/قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.irrigation_policy import IrrigationPolicy, policy_params  # noqa: E402


def test_water_saving_knobs():
    pp = policy_params(IrrigationPolicy.WATER_SAVING)
    assert pp.policy is IrrigationPolicy.WATER_SAVING
    assert pp.trigger_fraction == 1.0
    assert pp.refill_fraction == 0.80
    assert pp.allow_stress is True


def test_yield_max_knobs():
    pp = policy_params(IrrigationPolicy.YIELD_MAX)
    assert pp.trigger_fraction == 0.90
    assert pp.refill_fraction == 1.00
    assert pp.allow_stress is False


def test_string_policy_accepted():
    assert policy_params("yield_max").policy is IrrigationPolicy.YIELD_MAX


def test_profit_without_prices_falls_back():
    pp = policy_params(IrrigationPolicy.PROFIT)
    assert pp.policy is IrrigationPolicy.WATER_SAVING  # تراجع
    assert any("PROFIT يتطلّب" in n for n in pp.notes_ar)


def test_profit_with_prices_active_and_bounded():
    pp = policy_params(IrrigationPolicy.PROFIT, water_price_per_m3=0.05, yield_value_per_ha=2000.0)
    assert pp.policy is IrrigationPolicy.PROFIT
    assert 0.7 <= pp.refill_fraction <= 1.0
    assert any("heuristic" in n for n in pp.notes_ar)


def test_expensive_water_reduces_refill():
    cheap = policy_params(
        IrrigationPolicy.PROFIT, water_price_per_m3=0.01, yield_value_per_ha=5000.0
    )
    dear = policy_params(
        IrrigationPolicy.PROFIT, water_price_per_m3=0.10, yield_value_per_ha=2000.0
    )
    # ماء أغلى نسبةً ⇒ ملء أقلّ (عجز أعمق).
    assert dear.refill_fraction <= cheap.refill_fraction


def test_unknown_policy_falls_back():
    pp = policy_params("nonsense")
    assert pp.policy is IrrigationPolicy.WATER_SAVING
    assert any("غير معروفة" in n for n in pp.notes_ar)


def test_calibrated_false():
    assert policy_params(IrrigationPolicy.WATER_SAVING).calibrated is False
