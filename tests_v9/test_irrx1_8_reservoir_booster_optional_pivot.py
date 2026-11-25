import math
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


def test_synthetic_two_pivots_share_reservoir_volume_projection():
    """Synthetic 180 ha farm: 100 ha selected, the other 80 ha are not evaluated."""
    pivots = [
        PivotMachineInput(
            pivot_id=pid,
            name=pid,
            field_id=pid,
            radius_m=math.sqrt(500000 / math.pi),
            design_flow_m3_h=200,
            required_inlet_pressure_bar=3.2,
        )
        for pid in ("pivot-a", "pivot-b")
    ]
    req = base_request(pivots=pivots, requested=["pivot-a", "pivot-b"])
    req.required_gross_volume_m3 = 6000
    req.wells = [
        WellSupplyInput(well_id=f"synthetic-well-{i}", available_flow_m3_h=130)
        for i in range(3)
    ]
    req.reservoir = ReservoirInput(
        reservoir_id="synthetic-reservoir",
        capacity_m3=6250,
        current_volume_m3=6250,
        minimum_operating_volume_m3=500,
        evaporation_loss_m3_h=1,
        seepage_loss_m3_h=1,
    )
    req.booster = BoosterPumpInput(pump_id="synthetic-booster", design_flow_m3_h=400)
    result = calculate_reservoir_booster_network(req)
    assert sum(p["area_ha"] for p in result.selected_pivots) == pytest.approx(100)
    assert result.booster["required_flow_m3_h"] == 400
    balance = result.reservoir_balance
    assert balance["requested_runtime_h"] == 15
    assert balance["net_change_m3_h"] == -12
    assert balance["forecast_end_volume_m3"] == 6070
    assert balance["forecast_excess_inflow_m3"] == 0
    assert balance["forecast_shortfall_to_minimum_m3"] == 0
    assert 6250 + (390 - 400 - 2) * 15 == balance["forecast_end_volume_m3"]


def test_reservoir_projection_distinguishes_excess_and_unfeasible_drawdown():
    req = base_request()
    req.required_gross_volume_m3 = 3450
    req.reservoir = ReservoirInput(
        reservoir_id="r1",
        capacity_m3=6250,
        current_volume_m3=6250,
        minimum_operating_volume_m3=500,
    )
    req.wells = [WellSupplyInput(well_id="w1", available_flow_m3_h=390)]
    full = calculate_reservoir_booster_network(req)
    assert full.reservoir_balance["forecast_end_volume_m3"] == 6250
    assert full.reservoir_balance["forecast_excess_inflow_m3"] == 2400
    req.wells = []
    req.reservoir = ReservoirInput(
        reservoir_id="r1",
        capacity_m3=6250,
        current_volume_m3=1000,
        minimum_operating_volume_m3=500,
    )
    deficit = calculate_reservoir_booster_network(req)
    assert deficit.status == "fail"
    assert deficit.reservoir_balance["forecast_end_volume_m3"] is None
    assert deficit.reservoir_balance["forecast_shortfall_to_minimum_m3"] == 2950
    assert deficit.content_digest != full.content_digest


def test_reservoir_projection_digest_changes_with_requested_runtime():
    req = base_request()
    first = calculate_reservoir_booster_network(req)
    req.required_gross_volume_m3 += 230
    second = calculate_reservoir_booster_network(req)
    assert second.reservoir_balance["requested_runtime_h"] != (
        first.reservoir_balance["requested_runtime_h"]
    )
    assert first.content_digest != second.content_digest
