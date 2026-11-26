"""Water pumping scenario through the existing economics request and endpoint."""

import pytest
from api.farm_economics import cost_categories, estimate_pumping_cost
from api.feasibility_models import FeasibilityRequest, WaterCostScenario
from pydantic import ValidationError


def _grid_pumping_scenario(**overrides):
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
    request = FeasibilityRequest.model_validate(
        {
            "area_ha": 50,
            "yield_t_per_ha": 4,
            "price_per_t": 300,
            "water_cost_scenario": _grid_pumping_scenario(),
        }
    )
    assert request.water_cost_scenario.pumped_m3_per_ha == 3000
    result = estimate_pumping_cost(request.water_cost_scenario, request.area_ha)
    assert result["status"] == "estimated"
    assert result["currency"] == "USD"
    assert result["estimate"]["total_m3"] == 150000
    assert result["estimate"]["cost_mid_usd"] == 10215
    assert result["included_in_feasibility"] is False
    assert result["scope"] == "well_pumping_only"
    assert result["input_basis"] == "synthetic"


@pytest.mark.parametrize(
    "overrides",
    [
        {"grid_efficiency": None},
        {"grid_price_usd_per_kwh": None},
        {"diesel_price_usd_per_liter": 1},
        {"well_depth_m": True},
        {"source_ref": " "},
        {"pumped_m3_per_ha": -1},
    ],
)
def test_missing_or_invalid_inputs_not_assumed(overrides):
    with pytest.raises(ValidationError):
        WaterCostScenario.model_validate(_grid_pumping_scenario(**overrides))


def test_legacy_contract_unchanged():
    request = FeasibilityRequest(area_ha=50, yield_t_per_ha=4, price_per_t=300)
    assert request.water_cost_scenario is None


def test_unrepresentable_seasonal_cost_not_evaluated():
    result = estimate_pumping_cost(
        WaterCostScenario.model_validate(_grid_pumping_scenario()), 1e308
    )
    assert result["status"] == "not_evaluated"
    assert "estimate" not in result


@pytest.fixture
def pumping_http(monkeypatch):
    from secrets import token_urlsafe

    from api import main
    from core.canonical_schemas import UserRole, UserSchema
    from core.jwt_denylist import InMemoryDenylist
    from fastapi.testclient import TestClient

    key = token_urlsafe(48)
    monkeypatch.setattr(main, "JWT_SECRET", key)
    monkeypatch.setattr(main, "JWT_VERIFY_KEY", key)
    monkeypatch.setattr(main, "JWT_VERIFY_ALGORITHM", main.JWT_ALGORITHM)
    monkeypatch.setattr(main, "_DENYLIST", InMemoryDenylist())
    user = UserSchema(
        user_id="pump-reader", tenant_id="tenant-a", role=UserRole.MANAGER, name_ar="مدير الحقل"
    )
    client = TestClient(main.app)
    try:
        yield client, {"Authorization": f"Bearer {main.create_token(user)}"}
    finally:
        client.close()


def test_existing_endpoint_keeps_caller_costs_and_currency_separate(pumping_http):
    client, headers = pumping_http
    endpoint = "/api/v1/economics/feasibility"
    legacy = {"area_ha": 50, "yield_t_per_ha": 4, "price_per_t": 300, "total_cost": 10000}
    baseline = client.post(endpoint, json=legacy, headers=headers)
    assert baseline.status_code == 200
    posted = client.post(
        endpoint, json={**legacy, "water_cost_scenario": _grid_pumping_scenario()}, headers=headers
    )
    assert posted.status_code == 200
    result = posted.json()
    scenario = result.pop("water_cost_scenario")
    assert result == baseline.json()
    assert scenario["estimate"]["cost_mid_usd"] == 10215
    assert scenario["included_in_feasibility"] is False


def test_pumping_feasibility_requires_an_authenticated_http_request(pumping_http):
    client, _ = pumping_http
    payload = {
        "area_ha": 50,
        "yield_t_per_ha": 4,
        "price_per_t": 300,
        "water_cost_scenario": _grid_pumping_scenario(),
    }
    assert client.post("/api/v1/economics/feasibility", json=payload).status_code == 401


def test_pumping_support_and_solar_reference_volume():
    assert cost_categories()["supports_well_pumping_scenario"] is True
    description = WaterCostScenario.model_json_schema()["properties"]["solar_m3_per_year"][
        "description"
    ]
    assert "100 m" in description and "before dust" in description
    inputs = {
        "input_basis": "synthetic",
        "source_ref": "fixture:solar-reference",
        "pumped_m3_per_ha": 1200,
        "pump_type": "solar",
        "well_depth_m": 100,
        "solar_capital_usd": 30000,
        "solar_lifetime_years": 10,
        "solar_maintenance_annual_pct": 0,
        "solar_m3_per_year": 100000,
        "solar_dust_derate_pct": 0.2,
    }
    for depth, expected_usd in [(100, 2250), (200, 4500)]:
        scenario = WaterCostScenario.model_validate({**inputs, "well_depth_m": depth})
        assert estimate_pumping_cost(scenario, 50)["estimate"]["cost_mid_usd"] == expected_usd
