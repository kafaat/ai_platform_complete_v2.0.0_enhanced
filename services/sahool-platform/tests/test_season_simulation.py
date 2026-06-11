"""اختبارات محاكاة الموسم (api.season_simulation) — منطق نقيّ بالكامل.

يغطّي: تطبيع المحصول (عربي/إنجليزي/غير مُعرّف)، GDD اليومي (قصّ الأساس/السقف)،
منحنى LAI، الكتلة الحيويّة عبر RUE، احتياج الماء FAO-56، الإنتاج = الكتلة × HI،
الإجهاد المائي، النطاق والثقة، والتدهور الرشيق عند نقص المدخلات.
لا حاجة لقاعدة أو شبكة.
"""

from datetime import date

from api.season_simulation import (
    DayWeather,
    SimContext,
    gdd_day,
    normalize_crop,
    simulate_season,
)


def _warm_days(n: int, t_min: float = 14.0, t_max: float = 30.0, et0: float = 5.0):
    """سلسلة طقس دافئة منتظمة لمحاكاة مستقرّة."""
    return [DayWeather(t_min_c=t_min, t_max_c=t_max, et0_mm=et0, rain_mm=0.0) for _ in range(n)]


class TestNormalizeCrop:
    def test_known_english(self):
        key, known = normalize_crop("Wheat")
        assert key == "wheat"
        assert known is True

    def test_arabic_alias(self):
        key, known = normalize_crop("قمح")
        assert key == "wheat"
        assert known is True

    def test_unknown_crop_flagged(self):
        key, known = normalize_crop("dragonfruit")
        assert known is False

    def test_none_crop(self):
        key, known = normalize_crop(None)
        assert key == ""
        assert known is False


class TestGddDay:
    def test_basic_mean_minus_base(self):
        # mean=20, base=0 ⇒ 20
        assert gdd_day(10.0, 30.0, t_base=0.0, t_cap=40.0) == 20.0

    def test_base_subtracted(self):
        # mean=20, base=8 ⇒ 12
        assert gdd_day(10.0, 30.0, t_base=8.0, t_cap=40.0) == 12.0

    def test_cap_clips_high_temp(self):
        # tmax capped at 30: mean=(30+10)/2=20, base 0 ⇒ 20 (not 25)
        assert gdd_day(10.0, 40.0, t_base=0.0, t_cap=30.0) == 20.0

    def test_cold_day_is_zero(self):
        # both below base ⇒ 0, never negative
        assert gdd_day(-5.0, 2.0, t_base=8.0, t_cap=30.0) == 0.0

    def test_never_negative(self):
        assert gdd_day(0.0, 0.0, t_base=10.0, t_cap=30.0) == 0.0


class TestSimulateBasics:
    def test_empty_weather_returns_zero_and_flags(self):
        r = simulate_season(SimContext(crop="wheat", weather=[]))
        assert r.days_simulated == 0
        assert r.yield_kg_ha == 0.0
        assert r.confidence == 0.0
        assert any("طقس" in w for w in r.warnings_ar)

    def test_gdd_accumulates(self):
        r = simulate_season(SimContext(crop="wheat", weather=_warm_days(60)))
        # 60 days * (mean 22 - base 0) = 1320
        assert r.gdd_total == 1320.0

    def test_positive_yield_and_biomass(self):
        r = simulate_season(SimContext(crop="wheat", weather=_warm_days(120)))
        assert r.biomass_kg_ha > 0
        assert r.yield_kg_ha > 0
        # الإنتاج < الكتلة الحيويّة (HI < 1)
        assert r.yield_kg_ha < r.biomass_kg_ha

    def test_yield_range_brackets_central(self):
        r = simulate_season(SimContext(crop="wheat", weather=_warm_days(120)))
        assert r.yield_low_kg_ha < r.yield_kg_ha < r.yield_high_kg_ha

    def test_water_need_positive(self):
        r = simulate_season(SimContext(crop="wheat", weather=_warm_days(100)))
        # 100 days * et0 5 * Kc(~0.4..1.15) ⇒ several hundred mm
        assert r.water_need_mm > 100

    def test_lai_within_crop_cap(self):
        r = simulate_season(SimContext(crop="wheat", weather=_warm_days(120)))
        assert 0 < r.lai_max <= 5.5  # سقف القمح


class TestMaturityAndConfidence:
    def test_maturity_reached_with_enough_gdd(self):
        # wheat gdd_to_maturity=1800; 100 warm days * 22 = 2200 ⇒ reached
        r = simulate_season(SimContext(crop="wheat", weather=_warm_days(100)))
        assert r.maturity_reached is True

    def test_immature_season_warns(self):
        r = simulate_season(SimContext(crop="wheat", weather=_warm_days(20)))
        assert r.maturity_reached is False
        assert any("النضج" in w for w in r.warnings_ar)

    def test_confidence_capped(self):
        r = simulate_season(SimContext(crop="wheat", weather=_warm_days(120)))
        assert r.confidence <= 0.85

    def test_unknown_crop_lower_confidence_and_warned(self):
        known = simulate_season(SimContext(crop="wheat", weather=_warm_days(120)))
        unknown = simulate_season(SimContext(crop="dragonfruit", weather=_warm_days(120)))
        assert unknown.crop_recognized is False
        assert unknown.confidence < known.confidence
        assert any("غير مُعرّف" in w for w in unknown.warnings_ar)


class TestWaterStress:
    def test_deficit_reduces_yield(self):
        weather = _warm_days(120)
        full = simulate_season(
            SimContext(crop="wheat", weather=weather, irrigation_mm_total=1000.0)
        )
        deficit = simulate_season(
            SimContext(crop="wheat", weather=weather, irrigation_mm_total=10.0)
        )
        assert deficit.water_stress_factor < full.water_stress_factor
        assert deficit.yield_kg_ha < full.yield_kg_ha
        assert any("عجز مائي" in w for w in deficit.warnings_ar)

    def test_no_supply_assumes_no_stress(self):
        r = simulate_season(SimContext(crop="wheat", weather=_warm_days(120)))
        assert r.water_stress_factor == 1.0
        assert any("ريّ" in a for a in r.assumptions_ar)

    def test_stress_factor_floor(self):
        r = simulate_season(
            SimContext(crop="wheat", weather=_warm_days(120), irrigation_mm_total=0.0)
        )
        assert r.water_stress_factor >= 0.4


class TestEstimationAssumptions:
    def test_missing_et0_is_estimated_and_noted(self):
        # طقس بلا ET₀ ⇒ يُقدَّر (Hargreaves) ويُوسم في الافتراضات
        weather = [DayWeather(t_min_c=14.0, t_max_c=30.0, et0_mm=None) for _ in range(60)]
        r = simulate_season(SimContext(crop="wheat", weather=weather))
        assert r.water_need_mm > 0  # ET₀ مُقدَّر ⇒ احتياج موجب
        assert any("ET" in a for a in r.assumptions_ar)

    def test_solar_estimated_when_absent(self):
        # solar=None دائماً في المسار الحالي ⇒ يُقدَّر ويُوسم
        r = simulate_season(SimContext(crop="wheat", weather=_warm_days(60)))
        assert any("الإشعاع" in a for a in r.assumptions_ar)

    def test_sowing_date_passthrough(self):
        r = simulate_season(
            SimContext(crop="wheat", sowing_date=date(2026, 1, 1), weather=_warm_days(90))
        )
        assert r.days_simulated == 90


class TestCropDifferences:
    def test_c4_maize_vs_wheat_biomass(self):
        # نفس الطقس: للذرة RUE أعلى لكن t_base أعلى أيضاً — نتأكّد فقط من نواتج موجبة مختلفة
        weather = _warm_days(120, t_min=18.0, t_max=32.0)
        maize = simulate_season(SimContext(crop="maize", weather=weather))
        wheat = simulate_season(SimContext(crop="wheat", weather=weather))
        assert maize.biomass_kg_ha > 0
        assert wheat.biomass_kg_ha > 0
        # معاملاتهما تختلف ⇒ النتائج ليست متطابقة
        assert maize.yield_kg_ha != wheat.yield_kg_ha
