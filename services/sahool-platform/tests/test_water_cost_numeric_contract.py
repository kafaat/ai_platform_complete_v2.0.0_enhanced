"""Reject invalid pump economics without changing valid cost calculations."""

from dataclasses import replace

import pytest
from core.engines.water_cost import WaterCostInputs, seasonal_water_cost, water_cost_per_m3


@pytest.mark.parametrize(
    "pump_type, overrides",
    [
        ("diesel", {"diesel_kwh_per_liter": 0}),
        ("diesel", {"diesel_price_usd_per_liter": -1}),
        ("diesel", {"pump_efficiency": 0}),
        ("diesel", {"pump_efficiency": 1.1}),
        ("diesel", {"well_depth_m": -1}),
        ("diesel", {"well_depth_m": float("nan")}),
        ("diesel", {"well_depth_m": True}),
        ("diesel", {"well_depth_m": 10**1000}),
        ("grid", {"grid_price_usd_per_kwh": float("inf")}),
        ("grid", {"grid_efficiency": -0.2}),
        ("solar", {"solar_lifetime_years": 0}),
        ("solar", {"solar_m3_per_year": -1}),
        ("solar", {"solar_dust_derate_pct": 1}),
        ("solar", {"solar_maintenance_annual_pct": -0.1}),
        ("solar", {"solar_capital_usd": -100}),
        ("grid", {"well_depth_m": 1e308, "grid_price_usd_per_kwh": 1e308}),
    ],
)
def test_invalid_inputs_return_error(pump_type, overrides):
    inp = WaterCostInputs(
        100,
        pump_type,
        diesel_price_usd_per_liter=1,
        grid_price_usd_per_kwh=0.2,
        solar_capital_usd=10000,
        solar_m3_per_year=10000,
    )
    assert "error" in water_cost_per_m3(replace(inp, **overrides))


@pytest.mark.parametrize("water, area", [(-1, 1), (1, -1), (float("nan"), 1), (1e308, 1e308)])
def test_invalid_seasonal_volume_returns_error(water, area):
    inp = WaterCostInputs(100, "grid", grid_price_usd_per_kwh=0.2)
    assert "error" in seasonal_water_cost(inp, water, area)


@pytest.mark.parametrize(
    "inp, expected",
    [
        (WaterCostInputs(100, "diesel", diesel_price_usd_per_liter=1), 0.1457),
        (WaterCostInputs(100, "grid", grid_price_usd_per_kwh=0.2), 0.0681),
        (WaterCostInputs(100, "solar", solar_capital_usd=10000, solar_m3_per_year=10000), 0.2),
        (WaterCostInputs(100, "grid", grid_price_usd_per_kwh=0), 0),
    ],
)
def test_valid_estimates_unchanged(inp, expected):
    result = water_cost_per_m3(inp)
    assert result["mid"] == expected
    assert 0 <= result["low"] <= result["mid"] <= result["high"]
