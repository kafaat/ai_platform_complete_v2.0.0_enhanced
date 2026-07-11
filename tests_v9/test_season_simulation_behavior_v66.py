"""اختبارات سلوكيّة نقيّة لنموذج محاكاة المحصول (RUE / FAO-56).

الوحدة المُختبَرة: services/sahool-platform/api/season_simulation.py

تركيز هذا الملفّ على المنطق الداخليّ النقيّ المُشتقّ من تشغيل الدوالّ فعليّاً
(قِيَم التوكيدات استُنتجت بتشغيل الدالّة، لا بالتخمين): القصّ غير المتماثل في GDD،
شكل منحنى LAI (صعود/قمّة/شيخوخة) وتقييده بسقف المحصول، حساب الإشعاع المُمتصّ
عبر Beer-Lambert والـRS المرصود، رياضيّات ETc الموسمي عبر مراحل FAO-56، تطبيع
سلسلة fAPAR، والحتميّة، والحالات الحدّيّة (طقس فارغ/بارد/صفر أيّام).

مُكمّل لـservices/sahool-platform/tests/test_season_simulation.py — لا يكرّره؛
هنا توكيدات عدديّة دقيقة على الدوالّ الداخليّة (gdd_day, _lai_at, _absorbed_par,
_seasonal_water_need, _resolve_observed_fapar) وعلى تماسك simulate_season.
"""

import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

import math  # noqa: E402
from dataclasses import asdict  # noqa: E402
from datetime import date  # noqa: E402

from api.season_simulation import (  # noqa: E402
    _DEFAULT_SOLAR_MJ,
    _PAR_FRACTION,
    _YEMEN_SOLAR_BY_MONTH,
    DayWeather,
    SimContext,
    _absorbed_par,
    _absorbed_par_observed,
    _lai_at,
    _params_for,
    _resolve_observed_fapar,
    _seasonal_water_need,
    _solar_estimate,
    simulate_season,
)


def _warm_days(n, t_min=14.0, t_max=30.0, et0=5.0, rain=0.0):
    """سلسلة طقس دافئة منتظمة لمحاكاة مستقرّة."""
    return [DayWeather(t_min_c=t_min, t_max_c=t_max, et0_mm=et0, rain_mm=rain) for _ in range(n)]


def _gdd_series(crop, weather):
    """WS-C.1c Zero-Legacy: سلسلة GDD المحقونة (نمط الراوتر، صيغة modified) — الاختبارات
    مُستثناة من حارس الصيغ. المحاكاة لم تعد تحسب GDD محلّيّاً."""
    p = _params_for(crop if crop else "")
    base, cap = p.t_base_c, p.t_cap_c
    out = []
    for d in weather:
        tmax = max(min(d.t_max_c, cap), base)
        tmin = max(d.t_min_c, base)
        out.append(max(0.0, (tmax + tmin) / 2.0 - base))
    return out


def _sim(crop, weather, **kw):
    kw.setdefault("gdd_daily_override", _gdd_series(crop, weather))
    return simulate_season(SimContext(crop=crop, weather=weather, **kw))


# WS-C.1c Zero-Legacy: نواة gdd_day أُزيلت من المنصّة (مِلك المحرّك، وتُختبَر هناك).


# ─── LAI: شكل منحنى النموّ (صعود/قمّة/شيخوخة) ────────────────────────


class TestLaiCurveShape:
    def test_zero_when_gdd_maturity_nonpositive(self):
        assert _lai_at(500.0, 0.0, 5.5) == 0.0
        assert _lai_at(500.0, -10.0, 5.5) == 0.0

    def test_zero_at_start(self):
        assert _lai_at(0.0, 1800.0, 5.5) == 0.0

    def test_rises_during_growth_phase(self):
        early = _lai_at(0.2 * 1800, 1800.0, 5.5)
        later = _lai_at(0.6 * 1800, 1800.0, 5.5)
        assert 0.0 < early < later

    def test_peak_near_seventy_percent(self):
        peak = _lai_at(0.7 * 1800, 1800.0, 5.5)
        before = _lai_at(0.5 * 1800, 1800.0, 5.5)
        after = _lai_at(0.85 * 1800, 1800.0, 5.5)
        assert peak > before
        assert peak > after

    def test_senescence_to_quarter_at_maturity(self):
        # عند النضج (p=1) ينحدر إلى ~0.25·lai_max
        assert _lai_at(1800.0, 1800.0, 5.5) == pytest.approx(0.25 * 5.5)

    def test_never_exceeds_lai_max(self):
        lai_max = 5.5
        # عيّنات على طول المنحنى لا تتجاوز السقف
        for frac in (0.1, 0.3, 0.5, 0.7, 0.9, 1.0, 1.2):
            assert _lai_at(frac * 1800, 1800.0, lai_max) <= lai_max + 1e-9


# ─── الإشعاع المُمتصّ: Beer-Lambert مقابل RS المرصود ─────────────────


class TestAbsorbedPar:
    def test_modeled_zero_lai_absorbs_nothing(self):
        # 1 − e^(−k·0) = 0 ⇒ لا امتصاص
        assert _absorbed_par(20.0, 0.0, 0.55) == 0.0

    def test_modeled_increases_with_lai(self):
        low = _absorbed_par(20.0, 1.0, 0.55)
        high = _absorbed_par(20.0, 4.0, 0.55)
        assert 0.0 < low < high

    def test_modeled_bounded_by_incident_par(self):
        par = 20.0 * _PAR_FRACTION
        # حتّى عند LAI كبير جدّاً لا يتجاوز PAR الساقط
        assert _absorbed_par(20.0, 100.0, 0.55) <= par + 1e-9

    def test_modeled_matches_beer_lambert(self):
        solar, lai, k = 22.0, 2.5, 0.6
        expected = solar * _PAR_FRACTION * (1.0 - math.exp(-k * lai))
        assert _absorbed_par(solar, lai, k) == expected

    def test_observed_is_par_times_fapar(self):
        assert _absorbed_par_observed(20.0, 1.0) == pytest.approx(20.0 * _PAR_FRACTION)

    def test_observed_clamps_fapar_to_unit_interval(self):
        par = 20.0 * _PAR_FRACTION
        assert _absorbed_par_observed(20.0, 1.5) == pytest.approx(par)  # >1 → 1
        assert _absorbed_par_observed(20.0, -0.3) == 0.0  # <0 → 0


# ─── ETc الموسمي: رياضيّات مراحل FAO-56 ──────────────────────────────


class TestSeasonalWaterNeed:
    def test_empty_series_is_zero(self):
        assert _seasonal_water_need("wheat", []) == 0.0

    def test_exact_staged_sum_for_known_crop(self):
        # 10 أيّام، ET₀=5، قمح. التوزيع: initial 2، dev 3، mid 3، late 2.
        # Kc قمح: 0.40/0.75/1.15/0.40
        expected = 2 * 5 * 0.40 + 3 * 5 * 0.75 + 3 * 5 * 1.15 + 2 * 5 * 0.40
        assert _seasonal_water_need("wheat", [5.0] * 10) == pytest.approx(expected)

    def test_unknown_crop_uses_generic_kc(self):
        # محصول غير مُعرّف ⇒ منحنى Kc افتراضي 0.4/0.8/1.1/0.6
        expected = 2 * 5 * 0.4 + 3 * 5 * 0.8 + 3 * 5 * 1.1 + 2 * 5 * 0.6
        assert _seasonal_water_need("zzz-unknown", [5.0] * 10) == pytest.approx(expected)

    def test_scales_linearly_with_et0(self):
        single = _seasonal_water_need("wheat", [5.0] * 30)
        double = _seasonal_water_need("wheat", [10.0] * 30)
        assert double == pytest.approx(2.0 * single)

    def test_non_negative(self):
        assert _seasonal_water_need("wheat", [0.0] * 5) == 0.0


# ─── تطبيع fAPAR المرصود إلى سلسلة يوميّة ────────────────────────────


class TestResolveObservedFapar:
    def test_none_yields_no_series_no_invalid(self):
        assert _resolve_observed_fapar(None, 5) == (None, False)

    def test_scalar_repeats_per_day(self):
        series, invalid = _resolve_observed_fapar(0.5, 3)
        assert series == [0.5, 0.5, 0.5]
        assert invalid is False

    def test_out_of_range_scalar_flagged_invalid(self):
        assert _resolve_observed_fapar(1.5, 3) == (None, True)
        assert _resolve_observed_fapar(-0.1, 3) == (None, True)

    def test_bool_rejected(self):
        # bool ليس fAPAR صالحاً رغم أنّه فرع من int
        assert _resolve_observed_fapar(True, 3) == (None, True)

    def test_empty_list_flagged_invalid(self):
        assert _resolve_observed_fapar([], 3) == (None, True)

    def test_series_truncated_to_n_days(self):
        series, invalid = _resolve_observed_fapar([0.1, 0.2, 0.3, 0.4], 2)
        assert series == [0.1, 0.2]
        assert invalid is False

    def test_short_series_extended_with_last_value(self):
        series, invalid = _resolve_observed_fapar([0.1, 0.2], 5)
        assert series == [0.1, 0.2, 0.2, 0.2, 0.2]
        assert invalid is False


# ─── تقدير الإشعاع حين يغيب القياس ───────────────────────────────────


class TestSolarEstimate:
    def test_none_month_uses_annual_default(self):
        assert _solar_estimate(None) == _DEFAULT_SOLAR_MJ

    def test_known_month_uses_table(self):
        assert _solar_estimate(5) == _YEMEN_SOLAR_BY_MONTH[5]

    def test_out_of_range_month_falls_back_to_default(self):
        assert _solar_estimate(99) == _DEFAULT_SOLAR_MJ


# ─── السلوك الكامل: حتميّة، تماسك، حالات حدّيّة ──────────────────────


class TestSimulateConsistency:
    def test_deterministic_same_input_same_output(self):
        weather = _warm_days(90)
        a = _sim("wheat", weather)
        b = _sim("wheat", weather)
        assert asdict(a) == asdict(b)

    def test_yield_equals_biomass_times_hi_under_no_stress(self):
        # بلا عرض مائي ⇒ لا إجهاد (stress=1) ⇒ الإنتاج = الكتلة × HI
        r = _sim("wheat", _warm_days(120))
        p = _params_for("wheat")
        assert r.water_stress_factor == 1.0
        assert r.yield_kg_ha == pytest.approx(r.biomass_kg_ha * p.harvest_index, rel=1e-6)

    def test_uncertainty_band_is_plus_minus_twenty_percent(self):
        # الحدّان يُحسبان من الإنتاج المركزي ثمّ يُقرَّبان لخانة عشريّة واحدة،
        # فنسمح بهامش التقريب (±0.05) حول ±20٪.
        r = _sim("wheat", _warm_days(120))
        assert r.yield_low_kg_ha == pytest.approx(r.yield_kg_ha * 0.8, abs=0.05)
        assert r.yield_high_kg_ha == pytest.approx(r.yield_kg_ha * 1.2, abs=0.05)
        assert r.yield_low_kg_ha < r.yield_kg_ha < r.yield_high_kg_ha

    def test_cold_season_below_base_yields_nothing(self):
        # maize t_base=8؛ أيّام باردة ⇒ GDD=0 ⇒ لا LAI ⇒ لا كتلة ⇒ لا إنتاج
        cold = [DayWeather(t_min_c=-5.0, t_max_c=2.0, et0_mm=3.0) for _ in range(60)]
        r = simulate_season(SimContext(crop="maize", weather=cold))
        assert r.gdd_total == 0.0
        assert r.biomass_kg_ha == 0.0
        assert r.yield_kg_ha == 0.0
        assert r.maturity_reached is False

    def test_longer_season_no_less_biomass(self):
        # موسم أطول (بنفس الطقس اليوميّ) لا يُنقص الكتلة المتراكمة
        short = _sim("wheat", _warm_days(40))
        long = _sim("wheat", _warm_days(140))
        assert long.biomass_kg_ha >= short.biomass_kg_ha

    def test_all_outputs_non_negative(self):
        r = _sim("wheat", _warm_days(110))
        for value in (
            r.gdd_total,
            r.lai_max,
            r.biomass_kg_ha,
            r.yield_kg_ha,
            r.yield_low_kg_ha,
            r.yield_high_kg_ha,
            r.water_need_mm,
            r.water_stress_factor,
            r.confidence,
        ):
            assert value >= 0.0

    def test_sowing_date_selects_monthly_solar(self):
        # تاريخ بذر ⇒ تقدير إشعاع حسب الشهر بدل المتوسّط السنويّ ⇒ كتلة مختلفة
        weather = _warm_days(60)
        no_date = _sim("wheat", weather)
        # مايو (شهر 5) إشعاعه 25 > الافتراضي 21 ⇒ كتلة أعلى
        may = _sim("wheat", weather, sowing_date=date(2026, 5, 1))
        assert may.biomass_kg_ha != no_date.biomass_kg_ha
        assert may.biomass_kg_ha > no_date.biomass_kg_ha

    def test_rain_supply_enables_water_balance(self):
        # مطر موسمي ⇒ يظهر عرض مائي وعامل إجهاد محسوب (لا افتراض "ريّ كافٍ")
        weather = _warm_days(120, rain=8.0)
        r = _sim("wheat", weather)
        assert r.water_supply_mm is not None
        assert r.water_supply_mm == pytest.approx(120 * 8.0, rel=1e-6)
