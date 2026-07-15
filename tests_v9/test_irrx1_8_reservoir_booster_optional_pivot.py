import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "sahool-platform"))

pytestmark = pytest.mark.unit

from api.irrigation_engineering_workspace import (  # noqa: E402
    BoosterPumpInput,
    HydraulicSegmentInput,
    PivotMachineInput,
    ReservoirBoosterNetworkRequest,
    ReservoirInput,
    WellSupplyInput,
    calculate_reservoir_booster_network,
)


def base_request(*, pivots=None, requested=None):
    return ReservoirBoosterNetworkRequest(
        tenant_id="tenant-a",
        field_id="field-a",
        season_id="season-a",
        required_gross_volume_m3=11000,
        wells=[
            WellSupplyInput(well_id="w1", available_flow_m3_h=80),
            WellSupplyInput(well_id="w2", available_flow_m3_h=80),
            WellSupplyInput(well_id="w3", available_flow_m3_h=80),
        ],
        reservoir=ReservoirInput(
            reservoir_id="r1",
            capacity_m3=4000,
            current_volume_m3=3500,
            minimum_operating_volume_m3=500,
        ),
        booster=BoosterPumpInput(
            pump_id="b1", design_flow_m3_h=230, design_head_m=90, installed_motor_power_kw=80
        ),
        segments=[
            HydraulicSegmentInput(
                segment_id="m1",
                from_node="r1",
                to_node="field-a",
                length_m=1000,
                internal_diameter_mm=250,
                elevation_change_m=8,
                minor_loss_m=5,
            )
        ],
        pivots=pivots or [],
        requested_pivot_ids=requested or [],
        safety_margin_m=5,
    )


def test_pivot_is_optional_and_booster_network_still_calculates():
    result = calculate_reservoir_booster_network(base_request())
    assert result.pivot_mode == "none"
    assert result.selected_pivots == []
    assert result.booster["required_flow_m3_h"] == 230
    assert result.reservoir_balance["net_change_m3_h"] == 10


def test_selected_pivot_controls_flow_and_pressure():
    pivot = PivotMachineInput(
        pivot_id="p1",
        name="Pivot 1",
        field_id="field-a",
        radius_m=399,
        design_flow_m3_h=200,
        required_inlet_pressure_bar=3.2,
    )
    result = calculate_reservoir_booster_network(base_request(pivots=[pivot], requested=["p1"]))
    assert result.pivot_mode == "selected"
    assert result.booster["required_flow_m3_h"] == 200
    assert result.selected_pivots[0]["area_ha"] > 49


def test_reservoir_runtime_fails_closed_when_volume_is_insufficient():
    req = base_request()
    req.wells = [WellSupplyInput(well_id="w1", available_flow_m3_h=80)]
    req.required_gross_volume_m3 = 20000
    result = calculate_reservoir_booster_network(req)
    assert "RESERVOIR_VOLUME_INSUFFICIENT_FOR_REQUESTED_RUNTIME" in result.blocking_constraints
    assert result.status == "fail"


def test_unknown_requested_pivot_rejected():
    try:
        base_request(requested=["missing"])
    except ValueError as exc:
        assert "unknown requested pivot ids" in str(exc)
    else:
        raise AssertionError("expected validation error")
