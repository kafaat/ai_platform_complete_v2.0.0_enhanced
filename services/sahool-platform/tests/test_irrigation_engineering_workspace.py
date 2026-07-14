from api.irrigation_engineering_workspace import (
    ExecutionMode,
    IrrigationSystemSpecification,
    IrrigationSystemType,
    QualityStatus,
    WaterDemandInput,
    calculate_irrigation_engineering,
)


def _spec(**overrides):
    data = dict(
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="fld_1",
        season_id="sea_1",
        system_id="sys_1",
        name="Pivot 1",
        system_type=IrrigationSystemType.CENTER_PIVOT,
        execution_mode=ExecutionMode.MANUAL_ESTIMATED,
        irrigated_area_ha=50,
        application_efficiency=0.85,
        design_flow_lps=60,
        length_m=400,
        full_revolution_hours=12,
        mainline_length_m=800,
        mainline_internal_diameter_mm=250,
        required_terminal_pressure_bar=2.0,
        supply_voltage_v=400,
    )
    data.update(overrides)
    return IrrigationSystemSpecification(**data)


def test_vendor_metadata_does_not_change_domain_result():
    demand = WaterDemandInput(net_depth_mm=18, effective_rain_mm=2)
    a = calculate_irrigation_engineering(_spec(), demand)
    b = calculate_irrigation_engineering(
        _spec(manufacturer="Any Vendor", controller_vendor="Controller X", adapter_type="mqtt"),
        demand,
    )
    assert a.calculations == b.calculations
    assert b.capability_graph["supported_execution_modes"][-1] == "supervised"


def test_manual_operation_calculates_volume_runtime_and_blocks_ledger_until_confirmation():
    result = calculate_irrigation_engineering(_spec(), WaterDemandInput(net_depth_mm=17))
    assert result.status in {QualityStatus.PASS, QualityStatus.DEGRADED}
    assert result.calculations["gross_volume_m3"] == 10000.0
    assert result.calculations["runtime_h"] is not None
    assert result.manual_operation["requires_completion_confirmation"] is True
    assert result.manual_operation["ledger_update_allowed_before_confirmation"] is False


def test_measured_flow_is_preferred_over_design_flow():
    result = calculate_irrigation_engineering(
        _spec(design_flow_lps=60, measured_flow_lps=50), WaterDemandInput(net_depth_mm=10)
    )
    assert result.capability_graph["flow_source"] == "measured"
    assert result.calculations["flow_lps"] == 50
    assert result.manual_operation["execution_mode"] == "manual_measured"


def test_missing_flow_fails_closed_for_runtime_but_keeps_water_demand():
    result = calculate_irrigation_engineering(
        _spec(design_flow_lps=None, measured_flow_lps=None), WaterDemandInput(net_depth_mm=10)
    )
    assert result.status == QualityStatus.FAIL
    assert "FLOW_RATE_REQUIRED_FOR_RUNTIME" in result.blocking_constraints
    assert result.calculations["gross_volume_m3"] > 0
    assert result.calculations["runtime_h"] is None


def test_digest_is_stable_and_changes_with_demand():
    spec = _spec()
    a = calculate_irrigation_engineering(spec, WaterDemandInput(net_depth_mm=10))
    b = calculate_irrigation_engineering(spec, WaterDemandInput(net_depth_mm=10))
    c = calculate_irrigation_engineering(spec, WaterDemandInput(net_depth_mm=11))
    assert a.content_digest == b.content_digest
    assert a.content_digest != c.content_digest
