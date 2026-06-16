"""Tests for engines flagged as untested in review: fertility, water_cost, yield_interval."""

from core.engines import fertility, water_cost, yield_interval


class TestFertility:
    def test_fertiliser_need_deficit(self):
        r = fertility.fertiliser_need(
            "N", required_kg_ha=120, available_kg_ha=40, use_efficiency=0.5
        )
        assert r.deficit_kg_ha == 80
        assert r.fertiliser_kg_ha == 160  # deficit / efficiency

    def test_fertiliser_need_no_deficit(self):
        r = fertility.fertiliser_need("N", required_kg_ha=50, available_kg_ha=80)
        assert r.deficit_kg_ha == 0
        assert r.fertiliser_kg_ha == 0

    def test_mineralisation_half_life(self):
        # عند T_ref=20°م وQ10: k = 0.05 ثابت ⇒ نصف العمر = ln(2)/0.05 = 13.86 يوم.
        r = fertility.mineralisation_half_life_days(temp_c=20, cn_ratio=12)
        assert r["k_per_day"] == 0.05  # 0.05 * 2^((20-20)/10) = 0.05
        assert r["half_life_days"] == 13.9  # ln(2)/0.05 = 13.863 → 13.9
        assert r["high_cn_delay"] is False  # C:N=12 < 30 ⇒ لا تأخير

    def test_mineralisation_q10_faster_when_hotter(self):
        # رفع الحرارة 10°م يُضاعف k (Q10=2) ويُنصّف نصف العمر — سلوك فيزيائيّ فعليّ.
        cool = fertility.mineralisation_half_life_days(temp_c=20, cn_ratio=12)
        hot = fertility.mineralisation_half_life_days(temp_c=30, cn_ratio=12)
        assert hot["k_per_day"] == 0.1  # 0.05 * 2^1
        assert hot["half_life_days"] == 6.9  # ln(2)/0.1 = 6.931 → 6.9
        assert hot["k_per_day"] == 2 * cool["k_per_day"]

    def test_mineralisation_high_cn_boundary(self):
        # تثبيت الحدّ: C:N>30 (شرط `>` صارم) يُفعّل التأخير ×4، أمّا 30.0 بالضبط فلا.
        at = fertility.mineralisation_half_life_days(temp_c=25, cn_ratio=30.0)
        over = fertility.mineralisation_half_life_days(temp_c=25, cn_ratio=30.001)
        assert at["high_cn_delay"] is False  # 30.0 ليست > 30.0
        assert over["high_cn_delay"] is True  # 30.001 > 30.0
        # k عند 25°م = 0.05 * 2^0.5 = 0.07071 ⇒ نصف عمر أساس 9.8 يوم.
        assert at["half_life_days"] == 9.8
        assert over["half_life_days"] == round(at["half_life_days"] * 4.0, 1)  # 39.2

    def test_organic_matter_deficit_value(self):
        # "low_input" لا يطابق fallow/rotation ⇒ OM=1.0 يبقى.
        # عجز = 2.5-1.0 = 1.5؛ كومبوست = 1.5*20 = 30.0 طن/هكتار.
        r = fertility.organic_matter_recommendation(1.0, 2.5, "low_input")
        assert r["status"] == "ناقص"
        assert r["compost_tons_per_ha"] == 30.0
        assert r["current_om_pct"] == 1.0

    def test_organic_matter_fallow_degrades_baseline(self):
        # تاريخ fallow_3yr يخفض OM ×0.7 ⇒ 1.0→0.7؛ عجز 1.8؛ كومبوست 36.0 طن/هكتار.
        r = fertility.organic_matter_recommendation(1.0, 2.5, "fallow_3yr")
        assert r["current_om_pct"] == 0.7
        assert r["compost_tons_per_ha"] == 36.0

    def test_organic_matter_rotation_can_reach_optimal(self):
        # rotation يرفع OM ×1.1 ⇒ 2.4→2.64 ≥ 2.5 ⇒ مثاليّ، لا كومبوست (حدّ `>=`).
        r = fertility.organic_matter_recommendation(2.4, 2.5, "rotation")
        assert r["status"] == "مثالي"
        assert r["compost_tons_per_ha"] == 0.0

    def test_organic_matter_optimal_no_compost(self):
        # OM=3.0 ≥ 2.5 (الحدّ `>=`) ⇒ مثاليّ، صفر كومبوست.
        r = fertility.organic_matter_recommendation(3.0, 2.5, "low_input")
        assert r["status"] == "مثالي"
        assert r["compost_tons_per_ha"] == 0.0


class TestWaterCost:
    def test_diesel_cost_positive(self):
        inp = water_cost.WaterCostInputs(
            well_depth_m=120,
            pump_type="diesel",
            pump_efficiency=0.6,
            diesel_price_usd_per_liter=0.8,
            diesel_kwh_per_liter=3.0,
            solar_capital_usd=0,
            solar_lifetime_years=20,
            solar_maintenance_annual_pct=2,
            solar_m3_per_year=0,
            solar_dust_derate_pct=5,
            grid_price_usd_per_kwh=0.1,
            grid_efficiency=0.9,
        )
        r = water_cost.water_cost_per_m3(inp)
        # قيمة محسوبة بالضبط (لا مجرّد >0):
        #   kwh = 0.002725*120/0.6 = 0.545 ؛ لترات = 0.545/3.0 = 0.181667
        #   كلفة = 0.181667*0.8 = 0.145333 → 0.1453 $/م³.
        assert r["mid"] == 0.1453
        # النطاق ثابت: low = mid*0.8، high = mid*1.3 (يُحسب من الكلفة الخام لا من mid المُدوّر).
        assert r["low"] == 0.1163  # 0.145333*0.8 = 0.116267 → 0.1163
        assert r["high"] == 0.1889  # 0.145333*1.3 = 0.188933 → 0.1889
        assert r["low"] < r["mid"] < r["high"]  # النطاق يحيط بالوسط
        assert "basis" in r

    def test_diesel_cost_scales_linearly_with_depth(self):
        # الكلفة تتناسب طرديّاً مع العمق (طاقة الرفع ∝ الارتفاع): ضِعف العمق ⇒ ضِعف الكلفة.
        def make(depth):
            return water_cost.WaterCostInputs(
                well_depth_m=depth,
                pump_type="diesel",
                pump_efficiency=0.6,
                diesel_price_usd_per_liter=0.8,
                diesel_kwh_per_liter=3.0,
                solar_capital_usd=0,
                solar_lifetime_years=20,
                solar_maintenance_annual_pct=2,
                solar_m3_per_year=0,
                solar_dust_derate_pct=5,
                grid_price_usd_per_kwh=0.1,
                grid_efficiency=0.9,
            )

        r120 = water_cost.water_cost_per_m3(make(120))
        r240 = water_cost.water_cost_per_m3(make(240))
        # 0.002725*240/0.6/3.0*0.8 = 0.290667 → 0.2907 (ضِعف 0.1453 ضمن التدوير).
        assert r240["mid"] == 0.2907
        # ضِعف العمق ⇒ ضِعف الكلفة (مع تسامح تدوير ضئيل).
        assert abs(r240["mid"] - 2 * r120["mid"]) <= 0.0002

    def test_diesel_cost_drops_with_higher_efficiency(self):
        # كفاءة أعلى ⇒ كلفة أقل (الطاقة تُقسَم على الكفاءة).
        def make(eff):
            return water_cost.WaterCostInputs(
                well_depth_m=120,
                pump_type="diesel",
                pump_efficiency=eff,
                diesel_price_usd_per_liter=0.8,
                diesel_kwh_per_liter=3.0,
                solar_capital_usd=0,
                solar_lifetime_years=20,
                solar_maintenance_annual_pct=2,
                solar_m3_per_year=0,
                solar_dust_derate_pct=5,
                grid_price_usd_per_kwh=0.1,
                grid_efficiency=0.9,
            )

        low_eff = water_cost.water_cost_per_m3(make(0.5))
        high_eff = water_cost.water_cost_per_m3(make(0.6))
        assert low_eff["mid"] > high_eff["mid"]
        # η=0.5: 0.002725*120/0.5/3.0*0.8 = 0.1744 $/م³.
        assert low_eff["mid"] == 0.1744

    def test_diesel_missing_price_returns_error(self):
        # حارس الوحدات: سعر الديزل متقلّب يوميّاً ⇒ بدونه خطأ صريح لا رقم مُلفّق.
        inp = water_cost.WaterCostInputs(well_depth_m=120, pump_type="diesel", pump_efficiency=0.6)
        r = water_cost.water_cost_per_m3(inp)
        assert "error" in r and "mid" not in r

    def test_grid_cost_value(self):
        # المسار الشبكيّ: kwh = 0.002725*120/0.9 = 0.363333 ؛ كلفة = *0.1 = 0.0363 $/م³.
        inp = water_cost.WaterCostInputs(
            well_depth_m=120,
            pump_type="grid",
            grid_price_usd_per_kwh=0.1,
            grid_efficiency=0.9,
        )
        r = water_cost.water_cost_per_m3(inp)
        assert r["mid"] == 0.0363
        assert r["low"] == 0.0327  # mid_raw*0.9
        assert r["high"] == 0.0436  # mid_raw*1.2

    def test_seasonal_scales_with_area(self):
        inp = water_cost.WaterCostInputs(
            well_depth_m=120,
            pump_type="diesel",
            pump_efficiency=0.6,
            diesel_price_usd_per_liter=0.8,
            diesel_kwh_per_liter=3.0,
            solar_capital_usd=0,
            solar_lifetime_years=20,
            solar_maintenance_annual_pct=2,
            solar_m3_per_year=0,
            solar_dust_derate_pct=5,
            grid_price_usd_per_kwh=0.1,
            grid_efficiency=0.9,
        )
        r10 = water_cost.seasonal_water_cost(inp, etc_m3_per_ha=5000, area_ha=10)
        assert r10["cost_mid_usd"] == 7265.0 and r10["total_m3"] == 50000
        # تحقّق فعليّ من التحجيم بالمساحة (الاسم يَعِد به): ضعف المساحة ⇒ ضعف الكلفة.
        r20 = water_cost.seasonal_water_cost(inp, etc_m3_per_ha=5000, area_ha=20)
        assert r20["total_m3"] == 100000
        assert r20["cost_mid_usd"] == 2 * r10["cost_mid_usd"]


class TestYieldInterval:
    def test_pending_when_no_calibration(self):
        r = yield_interval.pending_estimate()
        assert r.status != "calibrated"
        assert r.point_estimate is None or r.lower is None

    def test_conformal_interval_brackets_estimate(self):
        residuals = [-0.5, 0.3, -0.2, 0.4, -0.1, 0.2, -0.3, 0.5, -0.4, 0.1]
        r = yield_interval.conformal_interval(5.0, residuals, coverage=0.9)
        assert r.lower <= r.point_estimate <= r.upper
        assert r.coverage == 0.9

    def test_conformal_wider_with_higher_coverage(self):
        residuals = [-0.5, 0.3, -0.2, 0.4, -0.1, 0.2, -0.3, 0.5, -0.4, 0.1]
        narrow = yield_interval.conformal_interval(5.0, residuals, coverage=0.8)
        wide = yield_interval.conformal_interval(5.0, residuals, coverage=0.95)
        assert (wide.upper - wide.lower) >= (narrow.upper - narrow.lower)


class TestRegionalSupplySignal:
    def test_strong_season_above_normal(self):
        from core.engines.market_analyzer import regional_supply_signal

        r = regional_supply_signal([4.2, 4.5, 4.0, 4.8, 4.3, 4.6], historical_avg_lai=3.5)
        assert r["signal"] == "above_normal"

    def test_weak_season_below_normal(self):
        from core.engines.market_analyzer import regional_supply_signal

        r = regional_supply_signal([2.0, 2.2, 1.8, 2.1, 1.9], historical_avg_lai=3.5)
        assert r["signal"] == "below_normal"

    def test_insufficient_data_unknown(self):
        from core.engines.market_analyzer import regional_supply_signal

        r = regional_supply_signal([3.0, 3.2], historical_avg_lai=None)
        assert r["signal"] == "unknown"

    def test_never_predicts_absolute_price(self):
        # HONESTY: must be a trend signal, never an absolute supply/price number
        from core.engines.market_analyzer import regional_supply_signal

        r = regional_supply_signal([4.2, 4.5, 4.0, 4.8, 4.3], historical_avg_lai=3.5)
        assert "تنبّؤ سعر" in r["note_ar"]  # explicitly says NOT a price forecast
        assert r["confidence"] == "low"
