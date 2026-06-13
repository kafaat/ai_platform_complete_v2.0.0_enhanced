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
        r = fertility.mineralisation_half_life_days(temp_c=20, cn_ratio=12)
        assert "half_life_days" in r
        assert r["half_life_days"] > 0

    def test_organic_matter_recommendation(self):
        r = fertility.organic_matter_recommendation(1.0, 2.5, "low_input")
        assert isinstance(r, dict)


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
        # قيمة محسوبة بالضبط (لا مجرّد >0): 120م، ديزل 0.8$/L، η0.6 ⇒ 0.1453$/م³.
        assert r["mid"] == 0.1453
        assert r["low"] < r["mid"] < r["high"]  # النطاق يحيط بالوسط
        assert "basis" in r

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
