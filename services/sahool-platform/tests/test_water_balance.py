"""اختبارات ميزان الماء (offline) — حساب فيزيائي بحت FAO-56.

يتحقّق من `api/water_balance.py`: ET0 (Hargreaves/Penman-Monteith)، الإشعاع
خارج الغلاف، المطر الفعّال (USDA-SCS)، معاملات Kc حسب المرحلة/المحصول، وفروع
التوصية (لا حاجة/منخفض/ري كامل). كلّ القيم مشتقّة من الكود نفسه، لا افتراضات.
بلا قاعدة بيانات ولا شبكة ولا قراءة ملفّات.
"""

import math

import pytest
from api import water_balance as wb
from api.water_balance import (
    ET0Method,
    WaterBalanceResult,
    WeatherInput,
    compute_et0,
    et0_hargreaves,
    et0_penman_monteith,
    water_balance,
)

pytestmark = pytest.mark.unit


# ─── WeatherInput.t_mean ───────────────────────────────────────────────────


def test_t_mean_defaults_to_average_of_min_max():
    assert WeatherInput(t_min_c=10, t_max_c=20).t_mean == 15.0


def test_t_mean_uses_explicit_value_when_given():
    assert WeatherInput(t_min_c=10, t_max_c=20, t_mean_c=18).t_mean == 18


# ─── الإشعاع خارج الغلاف Ra ────────────────────────────────────────────────


def test_extraterrestrial_radiation_known_value():
    ra = wb._extraterrestrial_radiation(15.5, 100)
    assert math.isclose(ra, 37.82882807649155, rel_tol=1e-9)


def test_extraterrestrial_radiation_positive_across_year():
    for doy in (1, 90, 180, 270, 365):
        assert wb._extraterrestrial_radiation(15.5, doy) > 0


# ─── Hargreaves ET0 ────────────────────────────────────────────────────────


def test_hargreaves_known_value():
    w = WeatherInput(t_min_c=15, t_max_c=30, latitude_deg=15.5, day_of_year=100)
    assert math.isclose(et0_hargreaves(w), 5.540660781927354, rel_tol=1e-9)


def test_hargreaves_formula_matches_manual():
    w = WeatherInput(t_min_c=15, t_max_c=30, latitude_deg=15.5, day_of_year=100)
    ra = wb._extraterrestrial_radiation(15.5, 100)
    expected = 0.0023 * (w.t_mean + 17.8) * math.sqrt(30 - 15) * ra * 0.408
    assert math.isclose(et0_hargreaves(w), expected, rel_tol=1e-12)


def test_hargreaves_clamps_negative_temp_range_to_zero():
    # t_max < t_min → sqrt(td) where td clamped to 0 → ET0 == 0
    w = WeatherInput(t_min_c=30, t_max_c=20)
    assert et0_hargreaves(w) == 0.0


# ─── Penman-Monteith ET0 ───────────────────────────────────────────────────


def test_penman_monteith_known_value():
    w = WeatherInput(t_min_c=15, t_max_c=30, solar_rad_mj_m2=25, rh_mean_pct=50, wind_2m_ms=2)
    assert math.isclose(et0_penman_monteith(w), 5.676429821349555, rel_tol=1e-9)


def test_penman_monteith_requires_all_inputs():
    # كلّ مدخل ناقص يرفع ValueError
    base = dict(t_min_c=15, t_max_c=30, solar_rad_mj_m2=25, rh_mean_pct=50, wind_2m_ms=2)
    for missing in ("solar_rad_mj_m2", "rh_mean_pct", "wind_2m_ms"):
        kwargs = dict(base)
        kwargs[missing] = None
        with pytest.raises(ValueError):
            et0_penman_monteith(WeatherInput(**kwargs))


def test_penman_monteith_non_negative():
    w = WeatherInput(t_min_c=2, t_max_c=4, solar_rad_mj_m2=1, rh_mean_pct=95, wind_2m_ms=0.1)
    assert et0_penman_monteith(w) >= 0.0


# ─── compute_et0 (اختيار الطريقة) ──────────────────────────────────────────


def test_compute_et0_prefers_penman_when_data_present():
    w = WeatherInput(t_min_c=15, t_max_c=30, solar_rad_mj_m2=25, rh_mean_pct=50, wind_2m_ms=2)
    et0, method = compute_et0(w)
    assert method == ET0Method.PENMAN_MONTEITH
    assert math.isclose(et0, 5.676429821349555, rel_tol=1e-9)


def test_compute_et0_falls_back_to_hargreaves():
    w = WeatherInput(t_min_c=15, t_max_c=30, latitude_deg=15.5, day_of_year=100)
    et0, method = compute_et0(w)
    assert method == ET0Method.HARGREAVES
    assert math.isclose(et0, 5.540660781927354, rel_tol=1e-9)


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


# ─── Kc + water_balance ────────────────────────────────────────────────────


def test_water_balance_known_crop_stage_kc():
    w = WeatherInput(t_min_c=15, t_max_c=30, latitude_deg=15.5, day_of_year=100)
    r = water_balance(w, "wheat", "mid", rain_mm=0)
    assert r.kc == 1.15
    assert r.kc_source_ar == "محصول مُعرّف (wheat)"
    assert r.method == ET0Method.HARGREAVES
    assert math.isclose(r.etc_mm, 5.540660781927354 * 1.15, rel_tol=1e-9)


def test_water_balance_unknown_crop_uses_default_curve():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = water_balance(w, "qat", "mid")
    # المنحنى الافتراضي: mid = 1.1
    assert r.kc == 1.1
    assert "غير مُعرّف" in r.kc_source_ar
    assert r.kc_source_ar.startswith("عامّ")


def test_water_balance_unknown_stage_defaults_kc_to_one():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = water_balance(w, "wheat", "bogus_stage")
    assert r.kc == 1.0


def test_water_balance_no_irrigation_branch_when_rain_covers_need():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = water_balance(w, "wheat", "mid", rain_mm=200)
    assert r.net_irrigation_mm == 0.0
    assert r.advice_ar.startswith("لا حاجة للريّ")


def test_water_balance_low_need_branch():
    # rain=4 → net ≈ 2.4 مم (0 < net < 5)
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = water_balance(w, "wheat", "mid", rain_mm=4)
    assert 0 < r.net_irrigation_mm < 5
    assert r.advice_ar.startswith("احتياج منخفض")


def test_water_balance_full_irrigation_branch():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = water_balance(w, "wheat", "mid", rain_mm=0)
    assert r.net_irrigation_mm >= 5
    assert r.advice_ar.startswith("الاحتياج الصافي")
    assert "hargreaves_samani" in r.advice_ar


def test_water_balance_net_equals_etc_minus_eff_rain_clamped():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = water_balance(w, "wheat", "mid", rain_mm=3)
    expected_net = max(0.0, r.etc_mm - r.effective_rain_mm)
    assert math.isclose(r.net_irrigation_mm, expected_net, rel_tol=1e-12)


# ─── WaterBalanceResult.to_dict ────────────────────────────────────────────


def test_result_to_dict_shape_and_rounding():
    w = WeatherInput(t_min_c=15, t_max_c=30, latitude_deg=15.5, day_of_year=100)
    d = water_balance(w, "wheat", "mid", rain_mm=0).to_dict()
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
    assert d["et0_mm"] == 5.54
    assert d["method"] == "hargreaves_samani"
    assert d["kc"] == 1.15
    assert d["etc_mm"] == 6.37


def test_result_dataclass_default_kc_source():
    r = WaterBalanceResult(
        et0_mm=1.0,
        method=ET0Method.HARGREAVES,
        kc=1.0,
        etc_mm=1.0,
        effective_rain_mm=0.0,
        net_irrigation_mm=1.0,
        advice_ar="x",
    )
    assert r.kc_source_ar == "محصول مُعرّف"
