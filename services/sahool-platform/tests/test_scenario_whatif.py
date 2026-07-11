"""اختبارات محرّك سيناريوهات "ماذا لو" (offline) — حساب فيزيائي بحت.

يتحقّق من `api/scenario_whatif.py`: تحويل الحرارة (أثر على ET0 والاحتياج)،
تغيير تاريخ الزراعة (أثر على GDD وبلوغ المرحلة)، وتغيّر المطر (أثر على صافي
الريّ). يعيد استخدام water_balance وtrack_gdd. القيم مشتقّة من الكود.
بلا قاعدة بيانات ولا شبكة ولا قراءة ملفّات.
"""

import pytest
from api.gdd_tracker import stage_result_from_cumulative
from api.scenario_whatif import (
    ScenarioComparison,
    whatif_planting_date,
    whatif_rainfall_change,
    whatif_temperature_shift,
)
from api.water_balance import WeatherInput, water_balance

pytestmark = pytest.mark.unit


# ─── ScenarioComparison.to_dict ────────────────────────────────────────────


def test_scenario_comparison_to_dict_rounding():
    c = ScenarioComparison("metric", 1.234, 2.345, 1.111, "مم")
    d = c.to_dict()
    assert d == {
        "metric_ar": "metric",
        "baseline": 1.23,
        "scenario": 2.35,
        "delta": 1.11,
        "unit": "مم",
    }


# ─── whatif_temperature_shift ──────────────────────────────────────────────


def test_temperature_shift_warmer_increases_water_need():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = whatif_temperature_shift(w, "wheat", "mid", 2.0, rain_mm=0)
    assert r["scenario_type"] == "temperature_shift"
    et0_cmp, net_cmp = r["comparisons"]
    assert et0_cmp["metric_ar"] == "ET0 المرجعي"
    # ارتفاع الحرارة يرفع ET0 ومن ثمّ الاحتياج (delta موجبة)
    assert et0_cmp["delta"] > 0
    assert net_cmp["delta"] > 0
    assert "ارتفاع" in r["summary_ar"]


def test_temperature_shift_baseline_matches_water_balance():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = whatif_temperature_shift(w, "wheat", "mid", 2.0, rain_mm=0)
    base = water_balance(w, "wheat", "mid", rain_mm=0)
    assert r["comparisons"][0]["baseline"] == round(base.et0_mm, 2)
    assert r["comparisons"][1]["baseline"] == round(base.net_irrigation_mm, 2)


def test_temperature_shift_scenario_applies_shift_to_both_temps():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    shift = 3.0
    r = whatif_temperature_shift(w, "wheat", "mid", shift, rain_mm=0)
    w2 = WeatherInput(t_min_c=15 + shift, t_max_c=30 + shift)
    scen = water_balance(w2, "wheat", "mid", rain_mm=0)
    assert r["comparisons"][0]["scenario"] == round(scen.et0_mm, 2)


def test_temperature_shift_cooler_uses_decrease_direction():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = whatif_temperature_shift(w, "wheat", "mid", -2.0)
    assert "انخفاض" in r["summary_ar"]


def test_temperature_shift_zero_baseline_need_avoids_div_by_zero():
    # مطر كثيف → الاحتياج الأساس = 0، لا قسمة على صفر، النسبة 0٪
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = whatif_temperature_shift(w, "wheat", "mid", 2.0, rain_mm=300)
    assert r["comparisons"][1]["baseline"] == 0.0
    assert "+0٪" in r["summary_ar"]


# ─── whatif_planting_date ──────────────────────────────────────────────────


# WS-C.1c Zero-Legacy: whatif_planting_date دالّة نقيّة تستقبل نتيجتَي GDD مُحقونتَين
# (من تراكميّ محرّك الطقس عبر stage_result_from_cumulative) — لا track_gdd محلّيّ.


def test_planting_date_same_stage_note():
    # base=150 (emergence)، scen=200 (emergence) — تراكميّ المحرّك مُحقون.
    base = stage_result_from_cumulative("wheat", 150.0, 10)
    scen = stage_result_from_cumulative("wheat", 200.0, 10)
    r = whatif_planting_date("wheat", base, scen)
    assert r["scenario_type"] == "planting_date"
    assert r["baseline_stage"] == r["scenario_stage"] == "emergence"
    gdd_cmp = r["comparisons"][0]
    assert gdd_cmp["baseline"] == 150.0
    assert gdd_cmp["scenario"] == 200.0
    assert gdd_cmp["delta"] == 50.0
    assert "كلا الموعدَين" in r["summary_ar"]


def test_planting_date_different_stage_note():
    base = stage_result_from_cumulative("wheat", 0.0, 5)  # planting
    scen = stage_result_from_cumulative("wheat", 250.0, 10)  # emergence
    r = whatif_planting_date("wheat", base, scen)
    assert r["baseline_stage"] == "planting"
    assert r["scenario_stage"] != "planting"
    assert "اختلاف المرحلة" in r["summary_ar"]


def test_planting_date_empty_baseline_series():
    base = stage_result_from_cumulative("wheat", 0.0, 0)
    scen = stage_result_from_cumulative("wheat", 200.0, 10)
    r = whatif_planting_date("wheat", base, scen)
    assert r["comparisons"][0]["baseline"] == 0.0
    assert r["baseline_stage"] == "planting"


# ─── whatif_rainfall_change ────────────────────────────────────────────────


def test_rainfall_change_more_rain_saves_irrigation():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = whatif_rainfall_change(w, "wheat", "mid", 0, 100)
    assert r["scenario_type"] == "rainfall_change"
    rain_cmp, net_cmp = r["comparisons"]
    assert rain_cmp["metric_ar"] == "المطر الفعّال"
    # المطر الفعّال يرتفع، والاحتياج الصافي ينخفض
    assert rain_cmp["delta"] > 0
    assert net_cmp["delta"] < 0
    assert "يوفّر" in r["summary_ar"]


def test_rainfall_change_baseline_matches_water_balance():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    r = whatif_rainfall_change(w, "wheat", "mid", 0, 100)
    base = water_balance(w, "wheat", "mid", rain_mm=0)
    scen = water_balance(w, "wheat", "mid", rain_mm=100)
    assert r["comparisons"][0]["baseline"] == round(base.effective_rain_mm, 2)
    assert r["comparisons"][0]["scenario"] == round(scen.effective_rain_mm, 2)
    assert r["comparisons"][1]["scenario"] == round(scen.net_irrigation_mm, 2)


def test_rainfall_change_less_rain_increases_irrigation():
    w = WeatherInput(t_min_c=15, t_max_c=30)
    # الأساس مطر وفير، البديل جفاف → الاحتياج يزيد (saved سالب)
    r = whatif_rainfall_change(w, "wheat", "mid", 100, 0)
    net_cmp = r["comparisons"][1]
    assert net_cmp["delta"] > 0
    assert "يزيد" in r["summary_ar"]
