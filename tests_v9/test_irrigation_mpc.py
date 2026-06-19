"""اختبار مُخطِّط الريّ التنبّؤيّ بالأفق المتحرّك (#376، MPC) — نقيّ حتميّ.

يثبت: (أ) WATER_SAVING يملأ جزئيّاً (0.8·Dr)؛ (ب) YIELD_MAX يملأ كاملاً (≈0)؛
(ج) YIELD_MAX يستهلك ماءً ≥ WATER_SAVING عبر نفس الأفق؛ (د) سقف الدفعة يُحترَم؛
(هـ) ميزانيّة الموسم لا تُتجاوَز (budget_exhausted)؛ (و) مطر/لا طلب ⇒ لا ريّ؛
(ز) تحت القصّ ⇒ إجهاد مُعلَّم؛ (ح) PROFIT بلا أسعار ⇒ سياسة water_saving. بلا شبكة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.irrigation_mpc import ForecastDay, plan_irrigation  # noqa: E402
from api.irrigation_policy import IrrigationPolicy  # noqa: E402


def _days(n, et0=10.0, kc=1.0, rain=0.0):
    return [ForecastDay(et0_mm=et0, kc=kc, rain_mm=rain) for _ in range(n)]


def test_water_saving_partial_refill():
    # TAW=100, p=0.5 ⇒ RAW=50. ETc=10/يوم. أوّل إطلاق عند Dr=50 ⇒ ملء 0.8×50=40 ⇒ Dr=10.
    plan = plan_irrigation(
        _days(6), taw_mm=100.0, raw_fraction=0.5, policy=IrrigationPolicy.WATER_SAVING
    )
    ev = next(d for d in plan.days if d.irrigation_mm > 0)
    assert ev.dr_before_irrig_mm == pytest.approx(50.0)
    assert ev.irrigation_mm == pytest.approx(40.0)  # 0.8 × 50
    assert ev.dr_end_mm == pytest.approx(10.0)


def test_yield_max_full_refill():
    plan = plan_irrigation(
        _days(6), taw_mm=100.0, raw_fraction=0.5, policy=IrrigationPolicy.YIELD_MAX
    )
    ev = next(d for d in plan.days if d.irrigation_mm > 0)
    assert ev.dr_end_mm == pytest.approx(0.0)  # ملء كامل حتى السعة الحقليّة


def test_yield_max_uses_at_least_as_much_water():
    fc = _days(20)
    ws = plan_irrigation(fc, taw_mm=100.0, raw_fraction=0.5, policy=IrrigationPolicy.WATER_SAVING)
    ym = plan_irrigation(fc, taw_mm=100.0, raw_fraction=0.5, policy=IrrigationPolicy.YIELD_MAX)
    # ميزان الماء: السقي الكامل يُبقي التربة أرطب ⇒ ماء كلّيّ ≥ الريّ العجزيّ.
    assert ym.total_irrigation_mm >= ws.total_irrigation_mm
    # m³/هكتار = مم × 10.
    assert ym.total_irrigation_m3_ha == pytest.approx(ym.total_irrigation_mm * 10.0)


def test_max_application_cap_respected():
    plan = plan_irrigation(
        _days(10, et0=30.0),
        taw_mm=100.0,
        raw_fraction=0.5,
        policy=IrrigationPolicy.WATER_SAVING,
        max_application_mm=20.0,
    )
    assert all(d.irrigation_mm <= 20.0 + 1e-9 for d in plan.days)


def test_season_budget_not_exceeded():
    plan = plan_irrigation(
        _days(30),
        taw_mm=100.0,
        raw_fraction=0.5,
        policy=IrrigationPolicy.YIELD_MAX,
        season_budget_mm=60.0,
    )
    assert plan.total_irrigation_mm <= 60.0 + 1e-9
    assert plan.budget_exhausted is True
    assert any("ميزانيّة" in n for n in plan.notes_ar)


def test_no_demand_no_irrigation():
    # مطر غزير يوميّاً ⇒ لا استنزاف ⇒ لا ريّ ولا إجهاد.
    plan = plan_irrigation(_days(10, et0=5.0, rain=100.0), taw_mm=100.0, raw_fraction=0.5)
    assert plan.total_irrigation_mm == 0.0
    assert plan.n_events == 0
    assert plan.stress_days == []


def test_under_irrigation_flags_stress():
    # ETc كبير + سقف دفعة صغير ⇒ Dr يبقى فوق RAW ⇒ إجهاد مُعلَّم.
    plan = plan_irrigation(
        _days(8, et0=30.0),
        taw_mm=100.0,
        raw_fraction=0.5,
        policy=IrrigationPolicy.WATER_SAVING,
        max_application_mm=20.0,
    )
    assert len(plan.stress_days) > 0
    assert any(d.stressed for d in plan.days)


def test_profit_without_prices_uses_water_saving():
    plan = plan_irrigation(
        _days(6), taw_mm=100.0, raw_fraction=0.5, policy=IrrigationPolicy.PROFIT_MAX
    )
    assert plan.policy == "water_saving"


def test_to_dict_keys():
    plan = plan_irrigation(_days(3), taw_mm=100.0, raw_fraction=0.5)
    d = plan.to_dict()
    assert set(d) >= {
        "policy",
        "taw_mm",
        "raw_mm",
        "total_irrigation_mm",
        "total_irrigation_m3_ha",
        "n_events",
        "stress_days",
        "final_depletion_mm",
        "days",
    }


def test_empty_forecast():
    plan = plan_irrigation([], taw_mm=100.0, raw_fraction=0.5)
    assert plan.days == []
    assert plan.total_irrigation_mm == 0.0
    assert plan.final_depletion_mm == 0.0
