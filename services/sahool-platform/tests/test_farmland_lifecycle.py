import pytest
from api.feasibility_models import FeasibilityRequest
from test_farmland_water_cost_feasibility import pumping_http  # noqa: F401


def comparison():
    options = []
    for kind, capital, price in [("grid", 100, 2), ("diesel", 200, 3), ("solar", 400, 0)]:
        options.append(
            dict(
                source=kind,
                annual_delivered_m3=1000,
                annual_energy_kwh=100,
                boq=[
                    dict(
                        item="equipment",
                        unit="set",
                        quantity=1,
                        unit_price=capital,
                        service_life_years=10,
                    )
                ],
                annual_maintenance=10,
                energy_price_per_kwh=price,
                source_ref="synthetic quote",
            )
        )
    return dict(currency="YER", horizon_years=2, discount_rate=0, baseline="grid", options=options)


def model(data):
    return FeasibilityRequest(
        area_ha=1, yield_t_per_ha=1, price_per_t=1, lifecycle_scenario=data
    ).lifecycle_scenario


def test_common_service_boq_cashflows_and_incremental_roi():
    report = model(comparison()).evaluate()
    grid, diesel, solar = report["options"]
    assert grid["discounted_cost"] == 520
    assert diesel["discounted_cost"] == 820
    assert solar["discounted_cost"] == 420
    assert solar["incremental_roi_pct"] == pytest.approx(100 / 300 * 100)
    assert grid["incremental_roi_pct"] is None
    assert report["currency"] == "YER"


def test_different_delivery_withholds_comparison():
    data = comparison()
    data["options"][2]["annual_delivered_m3"] = 500
    assert model(data).evaluate()["options"][2]["incremental_roi_pct"] is None


def test_replacements_and_discounting():
    data = comparison()
    data.update(discount_rate=0.1)
    data["options"][0]["boq"][0]["service_life_years"] = 1
    report = model(data).evaluate()["options"][0]
    assert report["replacement_total"] == 100
    assert report["discounted_cost"] == pytest.approx(100 + (210 + 100) / 1.1 + 210 / (1.1**2))


def test_all_three_sources_required():
    data = comparison()
    data["options"][2]["source"] = "grid"
    with pytest.raises(ValueError, match="three"):
        model(data)


def test_authenticated_lifecycle_scenario_uses_existing_route(pumping_http):
    client, headers = pumping_http
    payload = {
        "area_ha": 50,
        "yield_t_per_ha": 1,
        "price_per_t": 10,
        "lifecycle_scenario": comparison(),
    }
    endpoint = "/api/v1/economics/feasibility"
    assert client.post(endpoint, json=payload).status_code == 401
    response = client.post(endpoint, json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["lifecycle_scenario"]["options"][2]["discounted_cost"] == 420
