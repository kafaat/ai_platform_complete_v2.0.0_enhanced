"""Water pumping scenario through the existing economics request and endpoint."""

import pytest
from api.farm_economics import estimate_pumping_cost
from api.feasibility_models import FeasibilityRequest, WaterCostScenario
from pydantic import ValidationError


def _grid(**overrides):
    return {
        "input_basis": "synthetic",
        "source_ref": "fixture:pivot-1",
        "pumped_m3_per_ha": 3000,
        "pump_type": "grid",
        "well_depth_m": 100,
        "grid_price_usd_per_kwh": 0.2,
        "grid_efficiency": 0.8,
        **overrides,
    }


def test_explicit_water_cost_scenario():
    request = FeasibilityRequest.model_validate({
        "area_ha": 50, "yield_t_per_ha": 4, "price_per_t": 300,
        "water_cost_scenario": _grid(),
    })
    assert request.water_cost_scenario.pumped_m3_per_ha == 3000
    result = estimate_pumping_cost(request.water_cost_scenario, request.area_ha)
    assert result["status"] == "estimated"
    assert result["currency"] == "USD"
    assert result["estimate"]["total_m3"] == 150000
    assert result["estimate"]["cost_mid_usd"] == 10215
    assert result["included_in_feasibility"] is False
    assert result["scope"] == "well_pumping_only"
    assert result["input_basis"] == "synthetic"


@pytest.mark.parametrize("overrides", [
    {"grid_efficiency": None},
    {"grid_price_usd_per_kwh": None},
    {"diesel_price_usd_per_liter": 1},
    {"well_depth_m": True},
    {"source_ref": " "},
    {"pumped_m3_per_ha": -1},
])
def test_missing_or_invalid_inputs_not_assumed(overrides):
    with pytest.raises(ValidationError):
        WaterCostScenario.model_validate(_grid(**overrides))


def test_legacy_contract_unchanged():
    request = FeasibilityRequest(area_ha=50, yield_t_per_ha=4, price_per_t=300)
    assert request.water_cost_scenario is None


def test_unrepresentable_seasonal_cost_not_evaluated():
    result = estimate_pumping_cost(WaterCostScenario.model_validate(_grid()), 1e308)
    assert result["status"] == "not_evaluated"
    assert "estimate" not in result


def test_existing_endpoint_keeps_caller_costs_and_currency_separate():
    from api.routers.economics import economics_feasibility_endpoint

    legacy = FeasibilityRequest(area_ha=50, yield_t_per_ha=4, price_per_t=300,
                                total_cost=10000)
    baseline = economics_feasibility_endpoint(legacy, user=None)
    request = legacy.model_copy(update={"water_cost_scenario": WaterCostScenario.model_validate(_grid())})
    result = economics_feasibility_endpoint(request, user=None)
    scenario = result.pop("water_cost_scenario")
    assert result == baseline
    assert scenario["estimate"]["cost_mid_usd"] == 10215
    assert scenario["included_in_feasibility"] is False
