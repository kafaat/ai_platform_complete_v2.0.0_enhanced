from api.irrigation_engineering_workspace import (
    CropWaterContext,
    ExecutionMode,
    InteractiveIrrigationCalculationRequest,
    InteractiveWaterDemandInput,
    IrrigationSystemSpecification,
    IrrigationSystemType,
    PipeFittingsInput,
    QualityStatus,
    SoilWaterContext,
    WaterDemandInput,
    WeatherWaterContext,
    calculate_interactive_irrigation_engineering,
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


def test_interactive_manual_calculator_explains_volume_pressure_and_power():
    req = InteractiveIrrigationCalculationRequest(
        specification=_spec(
            application_efficiency=0.82,
            design_flow_lps=230 / 3.6,
            mainline_length_m=1000,
            mainline_internal_diameter_mm=200,
            elevation_change_m=8,
            required_terminal_pressure_bar=2.5,
            pump_efficiency=0.8,
            motor_efficiency=0.9,
        ),
        water_demand=InteractiveWaterDemandInput(
            mode="manual",
            manual_net_depth_mm=18,
            crop=CropWaterContext(crop_type="wheat", growth_stage="flowering", kc=1.15),
            soil=SoilWaterContext(soil_type="loam", infiltration_rate_mm_h=12),
            weather=WeatherWaterContext(et0_mm_day=6.4, effective_rain_mm=0),
        ),
        fittings=PipeFittingsInput(elbows_90=4, valves=2, check_valves=1, filters=1),
        safety_margin_m=5,
        installed_motor_power_kw=45,
    )
    result = calculate_interactive_irrigation_engineering(req)
    assert result.calculations["gross_volume_m3"] == 10975.61
    assert result.calculations["mainline_velocity_m_s"] > 2
    assert result.calculations["required_pressure_bar"] > 0
    assert result.calculations["required_input_power_kw"] > 45
    assert "INSTALLED_MOTOR_POWER_INSUFFICIENT" in result.blocking_constraints
    assert result.feasibility["execution_authorized"] is False


def test_interactive_sahool_mode_uses_soil_weather_crop_and_effective_rain():
    req = InteractiveIrrigationCalculationRequest(
        specification=_spec(application_efficiency=0.8),
        water_demand=InteractiveWaterDemandInput(
            mode="sahool",
            crop=CropWaterContext(crop_type="wheat", kc=1.0),
            soil=SoilWaterContext(depletion_mm=18, taw_mm=100, raw_mm=40),
            weather=WeatherWaterContext(et0_mm_day=6, forecast_days=1, effective_rain_mm=5),
        ),
    )
    result = calculate_interactive_irrigation_engineering(req)
    assert result.calculations["net_depth_mm"] == 19
    assert result.calculations["gross_depth_mm"] == 23.75
    assert "ETC_FROM_ET0_TIMES_KC" in result.explanations


def test_interactive_sahool_mode_requires_depletion_truth():
    req = InteractiveIrrigationCalculationRequest(
        specification=_spec(),
        water_demand=InteractiveWaterDemandInput(
            mode="sahool",
            crop=CropWaterContext(kc=1),
            weather=WeatherWaterContext(et0_mm_day=5),
        ),
    )
    import pytest

    with pytest.raises(ValueError, match="soil.depletion_mm"):
        calculate_interactive_irrigation_engineering(req)
