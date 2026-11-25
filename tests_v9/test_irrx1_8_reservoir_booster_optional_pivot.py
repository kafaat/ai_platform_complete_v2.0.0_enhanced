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
    """Generic shared-reservoir capability, not the Farmland owner topology."""
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
        WellSupplyInput(well_id=f"synthetic-well-{i}", available_flow_m3_h=130) for i in range(3)
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
    assert (
        second.reservoir_balance["requested_runtime_h"]
        != (first.reservoir_balance["requested_runtime_h"])
    )
    assert first.content_digest != second.content_digest


def test_farmland_independent_three_well_reservoir_booster_systems():
    """Synthetic 180 ha farm: two independent 50 ha pivots; 80 ha not evaluated."""

    def network(suffix, flows, capacity, current, evaporation, seepage):
        field = f"synthetic-pivot-{suffix}"
        reservoir = f"synthetic-reservoir-{suffix}"
        pivot = PivotMachineInput(
            pivot_id=field,
            name=field,
            field_id=field,
            radius_m=math.sqrt(500000 / math.pi),
            design_flow_m3_h=200,
            required_inlet_pressure_bar=3.2,
        )
        return ReservoirBoosterNetworkRequest(
            tenant_id="synthetic-farm",
            field_id=field,
            season_id="synthetic-wheat",
            required_gross_volume_m3=3000,
            wells=[
                WellSupplyInput(well_id=f"synthetic-{suffix}-well-{i}", available_flow_m3_h=q)
                for i, q in enumerate(flows, 1)
            ],
            reservoir=ReservoirInput(
                reservoir_id=reservoir,
                capacity_m3=capacity,
                current_volume_m3=current,
                minimum_operating_volume_m3=500,
                evaporation_loss_m3_h=evaporation,
                seepage_loss_m3_h=seepage,
            ),
            booster=BoosterPumpInput(
                pump_id=f"synthetic-booster-{suffix}",
                design_flow_m3_h=200,
                design_head_m=90,
                installed_motor_power_kw=100,
            ),
            segments=[
                HydraulicSegmentInput(
                    segment_id=f"synthetic-pipe-{suffix}",
                    from_node=reservoir,
                    to_node=field,
                    length_m=1000,
                    internal_diameter_mm=250,
                )
            ],
            pivots=[pivot],
            requested_pivot_ids=[field],
        )

    a = network("a", [80, 90, 100], 3500, 3000, 1, 1)
    b = network("b", [40, 50, 60], 2000, 1000, 1, 2)
    assert len({w.well_id for req in (a, b) for w in req.wells}) == 6
    assert a.reservoir.reservoir_id != b.reservoir.reservoir_id
    assert a.booster.pump_id != b.booster.pump_id
    first, second = (calculate_reservoir_booster_network(req) for req in (a, b))
    assert sum(r.selected_pivots[0]["area_ha"] for r in (first, second)) == pytest.approx(100)
    for result in (first, second):
        assert result.booster["required_flow_m3_h"] == 200
        assert result.booster["input_power_kw"] > 0
        assert result.reservoir_balance["requested_runtime_h"] == 15
    assert first.reservoir_balance["well_inflow_m3_h"] == 270
    assert second.reservoir_balance["well_inflow_m3_h"] == 150
    assert first.reservoir_balance["forecast_end_volume_m3"] == 3500
    assert first.reservoir_balance["forecast_excess_inflow_m3"] == 520
    assert first.status != "fail"
    assert second.reservoir_balance["forecast_end_volume_m3"] is None
    assert second.reservoir_balance["forecast_shortfall_to_minimum_m3"] == 295
    assert second.status == "fail"
    assert "RESERVOIR_VOLUME_INSUFFICIENT_FOR_REQUESTED_RUNTIME" in second.blocking_constraints
    # An aggregate surplus cannot make the second independent network feasible.
    assert first.reservoir_balance["forecast_excess_inflow_m3"] > 295
    assert first.content_digest != second.content_digest


def test_duplicate_well_cannot_double_count_network_supply():
    payload = base_request().model_dump()
    payload["wells"].append(payload["wells"][0].copy())
    with pytest.raises(ValueError, match="duplicate well ids"):
        ReservoirBoosterNetworkRequest.model_validate(payload)


def test_booster_requested_energy_uses_runtime_and_efficiency():
    req = base_request()
    result = calculate_reservoir_booster_network(req)
    assert result.booster["requested_energy_kwh"] == pytest.approx(
        result.booster["input_power_kw"] * result.reservoir_balance["requested_runtime_h"],
        rel=1e-5,
    )
    req.booster.pump_efficiency = 0.5
    less_efficient = calculate_reservoir_booster_network(req)
    assert less_efficient.booster["requested_energy_kwh"] > result.booster["requested_energy_kwh"]
    assert less_efficient.content_digest != result.content_digest


def test_blocked_network_energy_is_requested_not_delivered():
    req = base_request()
    req.wells = []
    result = calculate_reservoir_booster_network(req)
    assert result.status == "fail"
    assert result.reservoir_balance["forecast_end_volume_m3"] is None
    assert result.booster["requested_energy_kwh"] > 0


def test_reservoir_forecast_at_exact_minimum_retains_feasible_volume():
    req = base_request()
    req.wells = []
    req.required_gross_volume_m3 = 950
    req.booster.design_flow_m3_h = 235
    req.reservoir = ReservoirInput(
        reservoir_id="r1",
        capacity_m3=1000,
        current_volume_m3=1000,
        minimum_operating_volume_m3=50,
    )
    result = calculate_reservoir_booster_network(req)
    assert result.status == "pass"
    assert result.blocking_constraints == []
    assert result.reservoir_balance["forecast_end_volume_m3"] == 50
    assert result.reservoir_balance["forecast_shortfall_to_minimum_m3"] == 0


@pytest.mark.parametrize("required_volume_m3", [950.000001, 950.00000001])
def test_reservoir_forecast_preserves_small_real_shortfall(required_volume_m3):
    req = base_request()
    req.wells = []
    req.required_gross_volume_m3 = required_volume_m3
    req.booster.design_flow_m3_h = 235
    req.reservoir = ReservoirInput(
        reservoir_id="r1",
        capacity_m3=1000,
        current_volume_m3=1000,
        minimum_operating_volume_m3=50,
    )
    result = calculate_reservoir_booster_network(req)
    assert result.status == "fail"
    assert "RESERVOIR_VOLUME_INSUFFICIENT_FOR_REQUESTED_RUNTIME" in result.blocking_constraints
    assert result.reservoir_balance["forecast_end_volume_m3"] is None
