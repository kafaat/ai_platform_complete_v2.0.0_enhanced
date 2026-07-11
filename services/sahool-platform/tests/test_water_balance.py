"""اختبارات ميزان الماء (offline) — حساب فيزيائي بحت FAO-56.

يتحقّق من `api/water_balance.py`: المطر الفعّال (USDA-SCS)، معاملات Kc حسب
المرحلة/المحصول، وفروع التوصية (لا حاجة/منخفض/ري كامل). كلّ القيم مشتقّة من الكود
نفسه، لا افتراضات. بلا قاعدة بيانات ولا شبكة ولا قراءة ملفّات.

WS-C.1b Zero-Legacy: **لا نواة ET0 محلّيّة** — ET0 يُحقَن من منتج محرّك الطقس؛ هنا
نُمرّر قيمة مرجعيّة ثابتة (``_ET0`` = 6.0 مم/يوم) ونختبر حساب/سياسة الميزان فوقها
(النواة نفسها تُختبَر في خدمة الطقس). ``compute_et0``/``et0_*``/``ET0Method`` حُذفت.
"""

import math

import pytest
from api import water_balance as wb
from api.water_balance import (
    WaterBalanceResult,
    WeatherInput,
    water_balance,
)

pytestmark = pytest.mark.unit

# قيمة ET0 مرجعيّة محقونة (تحاكي منتج المحرّك) — نختبر منطق الميزان فوقها.
_ET0 = 6.0


# ─── WeatherInput.t_mean ───────────────────────────────────────────────────


def test_t_mean_defaults_to_average_of_min_max():
    assert WeatherInput(t_min_c=10, t_max_c=20).t_mean == 15.0


def test_t_mean_uses_explicit_value_when_given():
    assert WeatherInput(t_min_c=10, t_max_c=20, t_mean_c=18).t_mean == 18


# ─── المطر الفعّال (USDA-SCS) ──────────────────────────────────────────────


def test_effective_rain_zero_and_negative_return_zero():
    assert wb._effective_rain(0) == 0.0
    assert wb._effective_rain(-5) == 0.0


def test_effective_rain_below_75_uses_quadratic_branch():
    # rain * (125 - 0.2*rain) / 125
    assert math.isclose(wb._effective_rain(50), 50 * (125 - 0.2 * 50) / 125)
    assert wb._effective_rain(50) == 46.0


def test_effective_rain_at_threshold_75():
    assert wb._effective_rain(75) == 100.0


def test_effective_rain_above_75_uses_linear_branch():
    # 0.1*rain + 92.5
    assert wb._effective_rain(100) == pytest.approx(102.5)
    assert wb._effective_rain(100) == 0.1 * 100 + 92.5


# ─── Kc + water_balance (ET0 محقون من المحرّك) ─────────────────────────────


def test_water_balance_injected_et0_and_method_flow_through():
    w = WeatherInput(t_min_c=15, t_max_c=30, latitude_deg=15.5, day_of_year=100)
    r = water_balance(w, "wheat", "mid", rain_mm=0, et0_mm=_ET0, et0_method="hargreaves_fallback")
    # ET0 والطريقة يمرّان من الحقن (المحرّك المصدر الوحيد) بلا حساب محلّيّ.
    assert r.et0_mm == _ET0
    assert r.method == "hargreaves_fallback"


def test_water_balance_known_crop_stage_kc():
    w = WeatherInput(t_min_c=15, t_max_c=30, latitude_deg=15.5, day_of_year=100)
    r = water_balance(w, "wheat", "mid", rain_mm=0, et0_mm=_ET0)
    assert r.kc == 1.15
    assert r.kc_source_ar == "محصول مُعرّف (wheat)"
    assert math.isclose(r.etc_mm, _ET0 * 1.15, rel_tol=1e-9)


def test_water_balance_unknown_crop_uses_default_curve():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = water_balance(w, "qat", "mid", et0_mm=_ET0)
    # المنحنى الافتراضي: mid = 1.1
    assert r.kc == 1.1
    assert "غير مُعرّف" in r.kc_source_ar
    assert r.kc_source_ar.startswith("عامّ")


def test_water_balance_unknown_stage_defaults_kc_to_one():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = water_balance(w, "wheat", "bogus_stage", et0_mm=_ET0)
    assert r.kc == 1.0


def test_water_balance_no_irrigation_branch_when_rain_covers_need():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = water_balance(w, "wheat", "mid", rain_mm=200, et0_mm=_ET0)
    assert r.net_irrigation_mm == 0.0
    assert r.advice_ar.startswith("لا حاجة للريّ")


def test_water_balance_low_need_branch():
    # et0=6.0, kc=1.15 ⇒ etc=6.9؛ rain=4 ⇒ مطر فعّال ≈ 3.97 ⇒ net ≈ 2.93 (0 < net < 5)
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = water_balance(w, "wheat", "mid", rain_mm=4, et0_mm=_ET0)
    assert 0 < r.net_irrigation_mm < 5
    assert r.advice_ar.startswith("احتياج منخفض")


def test_water_balance_full_irrigation_branch():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = water_balance(w, "wheat", "mid", rain_mm=0, et0_mm=_ET0, et0_method="hargreaves_fallback")
    assert r.net_irrigation_mm >= 5
    assert r.advice_ar.startswith("الاحتياج الصافي")
    # الطريقة المحقونة تظهر في نصّ التوصية (شفّافيّة المصدر).
    assert "hargreaves_fallback" in r.advice_ar


def test_water_balance_net_equals_etc_minus_eff_rain_clamped():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = water_balance(w, "wheat", "mid", rain_mm=3, et0_mm=_ET0)
    expected_net = max(0.0, r.etc_mm - r.effective_rain_mm)
    assert math.isclose(r.net_irrigation_mm, expected_net, rel_tol=1e-12)


# ─── WaterBalanceResult.to_dict ────────────────────────────────────────────


def test_result_to_dict_shape_and_rounding():
    w = WeatherInput(t_min_c=15, t_max_c=30, latitude_deg=15.5, day_of_year=100)
    d = water_balance(
        w, "wheat", "mid", rain_mm=0, et0_mm=_ET0, et0_method="hargreaves_fallback"
    ).to_dict()
    assert set(d) == {
        "et0_mm",
        "method",
        "kc",
        "kc_source_ar",
        "etc_mm",
        "effective_rain_mm",
        "net_irrigation_mm",
        "advice_ar",
    }
    assert d["et0_mm"] == 6.0
    assert d["method"] == "hargreaves_fallback"  # طريقة المحرّك (نصّ)، لا enum محلّيّ
    assert d["kc"] == 1.15
    assert d["etc_mm"] == 6.9


def test_result_dataclass_default_kc_source():
    r = WaterBalanceResult(
        et0_mm=1.0,
        method="hargreaves_fallback",
        kc=1.0,
        etc_mm=1.0,
        effective_rain_mm=0.0,
        net_irrigation_mm=1.0,
        advice_ar="x",
    )
    assert r.kc_source_ar == "محصول مُعرّف"
