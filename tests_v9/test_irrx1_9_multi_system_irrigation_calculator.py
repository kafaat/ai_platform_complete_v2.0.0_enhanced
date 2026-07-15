import pytest
from api.irrigation_engineering_workspace import (
    BoosterPumpInput,
    HydraulicSegmentInput,
    IrrigationMachineInput,
    IrrigationSystemType,
    ReservoirBoosterNetworkRequest,
    ReservoirInput,
    WellSupplyInput,
    calculate_reservoir_booster_network,
)

pytestmark = pytest.mark.unit


def base_request(**kwargs):
    data = dict(
        tenant_id="t1",
        field_id="f1",
        required_gross_volume_m3=1000,
        wells=[WellSupplyInput(well_id="w1", available_flow_m3_h=100)],
        reservoir=ReservoirInput(
            reservoir_id="r1",
            capacity_m3=2000,
            current_volume_m3=1500,
            minimum_operating_volume_m3=200,
        ),
        booster=BoosterPumpInput(
            pump_id="b1", design_flow_m3_h=120, design_head_m=100, installed_motor_power_kw=100
        ),
        segments=[
            HydraulicSegmentInput(
                segment_id="s1",
                from_node="r1",
                to_node="m1",
                length_m=200,
                internal_diameter_mm=250,
            )
        ],
    )
    data.update(kwargs)
    return ReservoirBoosterNetworkRequest(**data)


def test_pump_only_remains_supported():
    result = calculate_reservoir_booster_network(base_request())
    assert result.machine_mode == "none"
    assert result.selected_machines == []


def test_drip_machine_supported_and_emitter_consistency_exposed():
    m = IrrigationMachineInput(
        machine_id="m1",
        name="drip",
        field_id="f1",
        system_type=IrrigationSystemType.DRIP,
        design_flow_m3_h=48,
        required_inlet_pressure_bar=1.5,
        zone_count=8,
        concurrent_zones=2,
        emitter_count=12000,
        emitter_flow_lph=4,
        wetted_area_ha=10,
    )
    result = calculate_reservoir_booster_network(
        base_request(irrigation_machines=[m], requested_machine_ids=["m1"])
    )
    assert result.machine_mode == "selected"
    assert result.selected_machines[0]["system_type"] == "drip"
    assert result.selected_machines[0]["emitter_aggregate_flow_m3_h"] == 48


def test_sprinkler_machine_supported():
    m = IrrigationMachineInput(
        machine_id="m1",
        name="sprinklers",
        field_id="f1",
        system_type=IrrigationSystemType.SPRINKLER,
        design_flow_m3_h=40,
        required_inlet_pressure_bar=3,
        sprinkler_count=20,
        sprinkler_flow_m3_h=2,
    )
    result = calculate_reservoir_booster_network(
        base_request(irrigation_machines=[m], requested_machine_ids=["m1"])
    )
    assert result.selected_machines[0]["sprinkler_aggregate_flow_m3_h"] == 40


def test_linear_and_reel_required_fields_fail_closed():
    import pytest

    with pytest.raises(ValueError):
        IrrigationMachineInput(
            machine_id="x",
            name="linear",
            field_id="f1",
            system_type="linear_move",
            design_flow_m3_h=30,
            required_inlet_pressure_bar=2,
        )
    with pytest.raises(ValueError):
        IrrigationMachineInput(
            machine_id="x",
            name="reel",
            field_id="f1",
            system_type="reel",
            design_flow_m3_h=30,
            required_inlet_pressure_bar=4,
        )


def test_valve_network_rejects_excess_concurrency():
    import pytest

    with pytest.raises(ValueError):
        IrrigationMachineInput(
            machine_id="x",
            name="valves",
            field_id="f1",
            system_type="valve_network",
            design_flow_m3_h=30,
            required_inlet_pressure_bar=2,
            zone_count=3,
            concurrent_zones=4,
        )
