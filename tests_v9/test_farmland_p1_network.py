"""Manual planning scenarios over the existing reservoir/booster calculation."""

import math

import pytest
from test_irrx1_8_reservoir_booster_optional_pivot import (
    PivotMachineInput,
    ReservoirBoosterNetworkRequest,
    base_request,
    calculate_reservoir_booster_network,
)

pytestmark = pytest.mark.unit


def request_for(field, season):
    pivot = PivotMachineInput(
        pivot_id=field,
        name=field,
        field_id=field,
        radius_m=math.sqrt(500000 / math.pi),
        design_flow_m3_h=200,
        required_inlet_pressure_bar=3,
    )
    req = base_request(pivots=[pivot], requested=[field]).model_dump()
    req.update(field_id=field, season_id=season, required_gross_volume_m3=400)
    for well in req["wells"]:
        well["well_id"] = field + well["well_id"]
    well_ids = [w["well_id"] for w in req["wells"]]
    req["wells"][0]["pumping_test"] = dict(
        source_ref="synthetic step 1",
        duration_min=120,
        static_level_m=15,
        pumping_level_m=20,
        discharge_m3_h=75,
    )
    req["reservoir"].update(reservoir_id=field + "-pond", current_volume_m3=550, capacity_m3=600)
    req["booster"]["pump_id"] = field + "-booster"
    req["segments"][0].update(from_node=field + "-pond", to_node=field)
    req["hourly_scenario"] = dict(
        source_ref="synthetic design",
        start_at="2026-01-01T00:00:00Z",
        curve=[
            dict(flow_m3_h=100, head_m=100, efficiency=0.8),
            dict(flow_m3_h=250, head_m=85, efficiency=0.75),
        ],
        pv=dict(capacity_kwp=120, derate=0.9, temperature_coefficient_per_c=-0.004),
        hours=[
            dict(
                demand_m3=200,
                well_inflows_m3_h=dict.fromkeys(well_ids, 0),
                irradiance_w_m2=0,
                ambient_temp_c=25,
            ),
            dict(
                demand_m3=200,
                well_inflows_m3_h=dict.fromkeys(well_ids, 80),
                irradiance_w_m2=1000,
                ambient_temp_c=25,
            ),
        ],
    )
    return req


def run(data):
    return calculate_reservoir_booster_network(ReservoirBoosterNetworkRequest(**data))


@pytest.mark.parametrize("season", ["winter", "summer"])
def test_180ha_farm_two_independent_50ha_pivots(season):
    results = [run(request_for(field, season)) for field in ("north", "south")]
    assert sum(r.selected_pivots[0]["area_ha"] for r in results) == pytest.approx(100)
    assert len({r.content_digest for r in results}) == 2
    for r in results:
        plan = r.reservoir_balance["hourly_scenario"]
        assert plan["hours"][0]["delivered_m3"] == 0
        second = plan["hours"][1]
        assert second["delivered_m3"] == pytest.approx(200)
        assert second["end_storage_m3"] == pytest.approx(590)
        assert second["energy_used_kwh"] > 0
        assert plan["unmet_m3"] == pytest.approx(200)
        test = next(iter(plan["pumping_tests"].values()))
        assert test["specific_capacity_m3_h_per_m"] == 15
        assert test["sustainable_yield_m3_h"] is None


def test_incomplete_hour_and_invalid_curve_rejected():
    r = request_for("east", "winter")
    r["hourly_scenario"]["hours"][0]["well_inflows_m3_h"].clear()
    with pytest.raises(ValueError, match="well"):
        run(r)
    r = request_for("east", "winter")
    r["hourly_scenario"]["curve"][1]["flow_m3_h"] = 100
    with pytest.raises(ValueError, match="curve"):
        run(r)


def test_inadequate_head_and_zero_reserve_cannot_deliver():
    r = request_for("east", "winter")
    for p in r["hourly_scenario"]["curve"]:
        p["head_m"] = 1
    plan = run(r).reservoir_balance["hourly_scenario"]
    assert plan["unmet_m3"] == 400
    assert plan["hours"][1]["spill_m3"] == 190
    assert "pump_head_below_tdh" in plan["constraints"]


def test_curve_rejects_extrapolation():
    r = request_for("east", "winter")
    r["hourly_scenario"]["curve"][1]["flow_m3_h"] = 150
    with pytest.raises(ValueError, match="curve"):
        run(r)


def test_fixed_duty_energy_cannot_be_averaged_over_a_dark_hour():
    data = request_for("north", "winter")
    data["hourly_scenario"]["hours"][1]["irradiance_w_m2"] = 1
    result = run(data).reservoir_balance["hourly_scenario"]
    assert result["hours"][1]["pv_kw"] > 0
    assert result["unmet_m3"] == 400
    assert result["hours"][1]["energy_used_kwh"] == 0


def test_network_export_has_serial_main_and_demand_in_lps():
    data = request_for("north", "winter")
    inp = run(data).reservoir_balance["hourly_scenario"]["epanet_duty_inp"]
    assert "UNITS LPS" in inp
    line = inp.split("[JUNCTIONS]\n")[1].splitlines()[0]
    assert float(line.split()[2]) == pytest.approx(200 / 3.6)
    data["segments"][0]["from_node"] = "other-pond"
    with pytest.raises(ValueError, match="serial main"):
        run(data)
