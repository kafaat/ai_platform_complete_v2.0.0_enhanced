"""IRR-X1 vendor-neutral irrigation engineering kernel.

Pure SI calculations and governed summaries for manual, supervised, and
adapter-backed irrigation systems. Vendor metadata is optional and never
changes the domain equations.
"""

from __future__ import annotations

import hashlib
import json
import math
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IrrigationSystemType(StrEnum):
    CENTER_PIVOT = "center_pivot"
    LINEAR_MOVE = "linear_move"
    REEL = "reel"
    SPRINKLER = "sprinkler"
    DRIP = "drip"
    PUMP_ONLY = "pump_only"
    VALVE_NETWORK = "valve_network"


class EvidenceLevel(StrEnum):
    MEASURED = "measured"
    COMMISSIONED = "commissioned"
    MANUFACTURER_SPEC = "manufacturer_spec"
    USER_DECLARED = "user_declared"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class ExecutionMode(StrEnum):
    RECOMMENDATION_ONLY = "recommendation_only"
    MANUAL_ESTIMATED = "manual_estimated"
    MANUAL_MEASURED = "manual_measured"
    SUPERVISED = "supervised"
    AUTOMATED = "automated"


class QualityStatus(StrEnum):
    PASS = "pass"
    DEGRADED = "degraded"
    FAIL = "fail"
    INCOMPLETE = "incomplete"


class EvidenceValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float | str | bool | None = None
    unit: str | None = None
    evidence_level: EvidenceLevel = EvidenceLevel.UNKNOWN
    source: str | None = None
    observed_at: str | None = None
    valid_until: str | None = None


class IrrigationSystemSpecification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    field_id: str
    season_id: str | None = None
    system_id: str
    name: str
    system_type: IrrigationSystemType
    manufacturer: str | None = None
    controller_vendor: str | None = None
    adapter_type: str | None = None
    execution_mode: ExecutionMode = ExecutionMode.RECOMMENDATION_ONLY

    irrigated_area_ha: float = Field(gt=0)
    application_efficiency: float = Field(default=0.8, gt=0, le=1)
    available_hours_per_day: float = Field(default=24.0, gt=0, le=24)
    design_flow_lps: float | None = Field(default=None, gt=0)
    measured_flow_lps: float | None = Field(default=None, gt=0)

    length_m: float | None = Field(default=None, gt=0)
    operating_arc_deg: float = Field(default=360.0, gt=0, le=360)
    full_revolution_hours: float | None = Field(default=None, gt=0)

    mainline_length_m: float = Field(default=0.0, ge=0)
    mainline_internal_diameter_mm: float | None = Field(default=None, gt=0)
    hazen_williams_c: float = Field(default=140.0, gt=0)
    elevation_change_m: float = 0.0
    minor_loss_m: float = Field(default=0.0, ge=0)
    required_terminal_pressure_bar: float | None = Field(default=None, ge=0)

    pump_efficiency: float = Field(default=0.72, gt=0, le=1)
    motor_efficiency: float = Field(default=0.9, gt=0, le=1)
    supply_voltage_v: float | None = Field(default=None, gt=0)
    power_factor: float = Field(default=0.85, gt=0, le=1)
    phases: int = Field(default=3, ge=1, le=3)

    evidence: dict[str, EvidenceValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def geometry_sanity(self) -> IrrigationSystemSpecification:
        if self.system_type == IrrigationSystemType.CENTER_PIVOT and self.length_m is None:
            raise ValueError("length_m is required for center_pivot")
        return self


class WaterDemandInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    net_depth_mm: float = Field(gt=0)
    effective_rain_mm: float = Field(default=0, ge=0)


class EngineeringResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: QualityStatus
    blocking_constraints: list[str]
    warnings: list[str]
    calculations: dict[str, float | None]
    capability_graph: dict[str, Any]
    manual_operation: dict[str, Any]
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _flow_lps(spec: IrrigationSystemSpecification) -> tuple[float | None, str]:
    if spec.measured_flow_lps is not None:
        return spec.measured_flow_lps, "measured"
    if spec.design_flow_lps is not None:
        return spec.design_flow_lps, "design"
    return None, "unknown"


def _hazen_williams_head_loss_m(
    flow_lps: float, length_m: float, diameter_mm: float, c: float
) -> float:
    # SI Hazen-Williams: h_f = 10.67 L Q^1.852 / (C^1.852 d^4.87)
    q_m3_s = flow_lps / 1000.0
    d_m = diameter_mm / 1000.0
    return 10.67 * length_m * (q_m3_s**1.852) / ((c**1.852) * (d_m**4.87))


def calculate_irrigation_engineering(
    spec: IrrigationSystemSpecification,
    demand: WaterDemandInput,
) -> EngineeringResult:
    warnings: list[str] = []
    blockers: list[str] = []
    flow_lps, flow_source = _flow_lps(spec)

    net_depth_mm = max(demand.net_depth_mm - demand.effective_rain_mm, 0.0)
    gross_depth_mm = net_depth_mm / spec.application_efficiency if net_depth_mm > 0 else 0.0
    net_volume_m3 = net_depth_mm * spec.irrigated_area_ha * 10.0
    gross_volume_m3 = gross_depth_mm * spec.irrigated_area_ha * 10.0

    flow_m3_h = flow_lps * 3.6 if flow_lps is not None else None
    runtime_h = gross_volume_m3 / flow_m3_h if flow_m3_h else None
    application_rate_mm_h = flow_m3_h / (spec.irrigated_area_ha * 10.0) if flow_m3_h else None
    max_daily_delivery_mm = (
        application_rate_mm_h * spec.available_hours_per_day if application_rate_mm_h else None
    )

    velocity_m_s = None
    friction_loss_m = None
    if flow_lps is not None and spec.mainline_internal_diameter_mm is not None:
        area_m2 = math.pi * (spec.mainline_internal_diameter_mm / 1000.0) ** 2 / 4.0
        velocity_m_s = (flow_lps / 1000.0) / area_m2
        friction_loss_m = _hazen_williams_head_loss_m(
            flow_lps,
            spec.mainline_length_m,
            spec.mainline_internal_diameter_mm,
            spec.hazen_williams_c,
        )
        if velocity_m_s > 3.0:
            warnings.append("MAINLINE_VELOCITY_HIGH")
        elif velocity_m_s < 0.3:
            warnings.append("MAINLINE_VELOCITY_LOW")

    terminal_head_m = (spec.required_terminal_pressure_bar or 0.0) * 10.19716213
    tdh_m = None
    hydraulic_power_kw = None
    input_power_kw = None
    current_a = None
    if flow_lps is not None:
        tdh_m = max(
            terminal_head_m
            + (friction_loss_m or 0.0)
            + spec.elevation_change_m
            + spec.minor_loss_m,
            0.0,
        )
        hydraulic_power_kw = 9.80665 * (flow_lps / 1000.0) * tdh_m
        input_power_kw = hydraulic_power_kw / (spec.pump_efficiency * spec.motor_efficiency)
        if spec.supply_voltage_v and spec.phases == 3:
            current_a = (
                input_power_kw * 1000.0 / (math.sqrt(3) * spec.supply_voltage_v * spec.power_factor)
            )
        elif spec.supply_voltage_v:
            current_a = input_power_kw * 1000.0 / (spec.supply_voltage_v * spec.power_factor)

    if flow_lps is None:
        blockers.append("FLOW_RATE_REQUIRED_FOR_RUNTIME")
    if spec.mainline_length_m > 0 and spec.mainline_internal_diameter_mm is None:
        blockers.append("MAINLINE_DIAMETER_REQUIRED")
    if spec.required_terminal_pressure_bar is None:
        warnings.append("TERMINAL_PRESSURE_UNKNOWN")

    revolutions = None
    speed_percent = None
    if (
        spec.system_type == IrrigationSystemType.CENTER_PIVOT
        and runtime_h
        and spec.full_revolution_hours
    ):
        revolutions = runtime_h / spec.full_revolution_hours
        speed_percent = min(100.0, 100.0 / revolutions) if revolutions > 0 else 100.0

    supported_modes = [ExecutionMode.RECOMMENDATION_ONLY.value]
    if flow_lps is not None:
        supported_modes.append(ExecutionMode.MANUAL_ESTIMATED.value)
    if spec.measured_flow_lps is not None:
        supported_modes.append(ExecutionMode.MANUAL_MEASURED.value)
    if spec.adapter_type:
        supported_modes.append(ExecutionMode.SUPERVISED.value)

    status = (
        QualityStatus.FAIL
        if blockers
        else (QualityStatus.DEGRADED if warnings else QualityStatus.PASS)
    )
    calc: dict[str, float | None] = {
        "net_depth_mm": round(net_depth_mm, 4),
        "gross_depth_mm": round(gross_depth_mm, 4),
        "net_volume_m3": round(net_volume_m3, 3),
        "gross_volume_m3": round(gross_volume_m3, 3),
        "flow_lps": round(flow_lps, 4) if flow_lps is not None else None,
        "flow_m3_h": round(flow_m3_h, 4) if flow_m3_h is not None else None,
        "runtime_h": round(runtime_h, 4) if runtime_h is not None else None,
        "application_rate_mm_h": round(application_rate_mm_h, 5)
        if application_rate_mm_h is not None
        else None,
        "max_daily_delivery_mm": round(max_daily_delivery_mm, 4)
        if max_daily_delivery_mm is not None
        else None,
        "mainline_velocity_m_s": round(velocity_m_s, 4) if velocity_m_s is not None else None,
        "mainline_friction_loss_m": round(friction_loss_m, 4)
        if friction_loss_m is not None
        else None,
        "pump_tdh_m": round(tdh_m, 4) if tdh_m is not None else None,
        "hydraulic_power_kw": round(hydraulic_power_kw, 4)
        if hydraulic_power_kw is not None
        else None,
        "input_power_kw": round(input_power_kw, 4) if input_power_kw is not None else None,
        "estimated_current_a": round(current_a, 3) if current_a is not None else None,
        "estimated_revolutions": round(revolutions, 4) if revolutions is not None else None,
        "recommended_speed_percent": round(speed_percent, 2) if speed_percent is not None else None,
    }
    capability = {
        "system_type": spec.system_type.value,
        "flow_source": flow_source,
        "maximum_flow_m3_h": calc["flow_m3_h"],
        "maximum_daily_delivery_mm": calc["max_daily_delivery_mm"],
        "minimum_operating_pressure_bar": spec.required_terminal_pressure_bar,
        "estimated_input_power_kw": calc["input_power_kw"],
        "supported_execution_modes": sorted(set(supported_modes)),
        "commissioning_status": "not_certified",
        "blocking_constraints": blockers,
    }
    manual = {
        "execution_mode": (
            ExecutionMode.MANUAL_MEASURED.value
            if spec.measured_flow_lps is not None
            else ExecutionMode.MANUAL_ESTIMATED.value
            if flow_lps is not None
            else ExecutionMode.RECOMMENDATION_ONLY.value
        ),
        "target_depth_mm": calc["gross_depth_mm"],
        "target_volume_m3": calc["gross_volume_m3"],
        "estimated_runtime_h": calc["runtime_h"],
        "recommended_speed_percent": calc["recommended_speed_percent"],
        "requires_completion_confirmation": True,
        "ledger_update_allowed_before_confirmation": False,
    }
    payload = {
        "specification": spec.model_dump(mode="json"),
        "demand": demand.model_dump(mode="json"),
        "status": status.value,
        "blocking_constraints": blockers,
        "warnings": warnings,
        "calculations": calc,
        "capability_graph": capability,
        "manual_operation": manual,
    }
    return EngineeringResult(
        status=status,
        blocking_constraints=blockers,
        warnings=warnings,
        calculations=calc,
        capability_graph=capability,
        manual_operation=manual,
        content_digest=_digest(payload),
    )


# ── IRR-X1.7 Interactive Irrigation Engineering Calculator ──────────────────
class CropWaterContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    crop_type: str | None = None
    growth_stage: str | None = None
    kc: float | None = Field(default=None, gt=0, le=2.5)
    root_depth_m: float | None = Field(default=None, gt=0, le=5)
    allowable_depletion_fraction: float | None = Field(default=None, gt=0, le=1)


class SoilWaterContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    soil_type: str | None = None
    taw_mm: float | None = Field(default=None, ge=0)
    raw_mm: float | None = Field(default=None, ge=0)
    depletion_mm: float | None = Field(default=None, ge=0)
    infiltration_rate_mm_h: float | None = Field(default=None, gt=0)
    moisture_quality: EvidenceLevel = EvidenceLevel.UNKNOWN


class WeatherWaterContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    et0_mm_day: float | None = Field(default=None, ge=0)
    forecast_days: float = Field(default=1.0, gt=0, le=14)
    effective_rain_mm: float = Field(default=0.0, ge=0)
    forecast_quality: EvidenceLevel = EvidenceLevel.UNKNOWN


class PipeFittingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    elbows_90: int = Field(default=0, ge=0, le=1000)
    valves: int = Field(default=0, ge=0, le=1000)
    check_valves: int = Field(default=0, ge=0, le=1000)
    filters: int = Field(default=0, ge=0, le=1000)
    custom_minor_loss_m: float = Field(default=0.0, ge=0)


class InteractiveWaterDemandInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str = Field(default="sahool", pattern=r"^(sahool|manual)$")
    manual_net_depth_mm: float | None = Field(default=None, gt=0)
    crop: CropWaterContext = Field(default_factory=CropWaterContext)
    soil: SoilWaterContext = Field(default_factory=SoilWaterContext)
    weather: WeatherWaterContext = Field(default_factory=WeatherWaterContext)

    @model_validator(mode="after")
    def validate_mode(self) -> InteractiveWaterDemandInput:
        if self.mode == "manual" and self.manual_net_depth_mm is None:
            raise ValueError("manual_net_depth_mm is required when mode=manual")
        return self


class InteractiveIrrigationCalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specification: IrrigationSystemSpecification
    water_demand: InteractiveWaterDemandInput
    fittings: PipeFittingsInput = Field(default_factory=PipeFittingsInput)
    safety_margin_m: float = Field(default=5.0, ge=0, le=100)
    installed_motor_power_kw: float | None = Field(default=None, gt=0)


class InteractiveIrrigationCalculationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: QualityStatus
    calculations: dict[str, float | None]
    water_demand: dict[str, Any]
    hydraulics: dict[str, Any]
    pump_energy: dict[str, Any]
    feasibility: dict[str, Any]
    warnings: list[str]
    blocking_constraints: list[str]
    explanations: list[str]
    assumptions: list[str]
    input_quality: dict[str, str]
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def _derive_interactive_net_depth(
    demand: InteractiveWaterDemandInput,
) -> tuple[float, list[str], list[str]]:
    explanations: list[str] = []
    assumptions: list[str] = []
    if demand.mode == "manual":
        assert demand.manual_net_depth_mm is not None
        explanations.append("WATER_DEMAND_MANUAL_OVERRIDE")
        return demand.manual_net_depth_mm, explanations, assumptions

    soil = demand.soil
    weather = demand.weather
    crop = demand.crop
    if soil.depletion_mm is None:
        raise ValueError("soil.depletion_mm is required when mode=sahool")

    forecast_etc = 0.0
    if weather.et0_mm_day is not None and crop.kc is not None:
        forecast_etc = weather.et0_mm_day * crop.kc * weather.forecast_days
        explanations.append("ETC_FROM_ET0_TIMES_KC")
    else:
        assumptions.append("FORECAST_ETC_NOT_INCLUDED_MISSING_ET0_OR_KC")

    net_depth = max(soil.depletion_mm + forecast_etc - weather.effective_rain_mm, 0.0)
    explanations.append("NET_DEPTH_EQUALS_DEPLETION_PLUS_FORECAST_ETC_MINUS_EFFECTIVE_RAIN")
    if soil.taw_mm is not None:
        if net_depth > soil.taw_mm:
            net_depth = soil.taw_mm
            explanations.append("NET_DEPTH_CAPPED_AT_TAW")
    if soil.raw_mm is not None and soil.depletion_mm > soil.raw_mm:
        explanations.append("SOIL_DEPLETION_EXCEEDS_RAW")
    return net_depth, explanations, assumptions


def _estimated_minor_loss_m(
    flow_lps: float | None, diameter_mm: float | None, fittings: PipeFittingsInput
) -> float:
    if flow_lps is None or diameter_mm is None:
        return fittings.custom_minor_loss_m
    area_m2 = math.pi * (diameter_mm / 1000.0) ** 2 / 4.0
    velocity = (flow_lps / 1000.0) / area_m2
    velocity_head = velocity**2 / (2 * 9.80665)
    k_total = (
        fittings.elbows_90 * 0.9
        + fittings.valves * 0.2
        + fittings.check_valves * 2.0
        + fittings.filters * 3.0
    )
    return k_total * velocity_head + fittings.custom_minor_loss_m


def calculate_interactive_irrigation_engineering(
    req: InteractiveIrrigationCalculationRequest,
) -> InteractiveIrrigationCalculationResult:
    net_depth_mm, explanations, assumptions = _derive_interactive_net_depth(req.water_demand)
    base = calculate_irrigation_engineering(
        req.specification,
        WaterDemandInput(net_depth_mm=max(net_depth_mm, 0.0001), effective_rain_mm=0),
    )
    calc = dict(base.calculations)
    flow_lps, flow_source = _flow_lps(req.specification)
    fittings_loss_m = _estimated_minor_loss_m(
        flow_lps,
        req.specification.mainline_internal_diameter_mm,
        req.fittings,
    )
    terminal_head_m = (req.specification.required_terminal_pressure_bar or 0.0) * 10.19716213
    tdh_m = None
    hydraulic_power_kw = None
    input_power_kw = None
    required_pressure_bar = None
    if flow_lps is not None:
        tdh_m = max(
            terminal_head_m
            + (calc.get("mainline_friction_loss_m") or 0.0)
            + fittings_loss_m
            + req.specification.elevation_change_m
            + req.safety_margin_m,
            0.0,
        )
        required_pressure_bar = tdh_m / 10.19716213
        hydraulic_power_kw = 9.80665 * (flow_lps / 1000.0) * tdh_m
        input_power_kw = hydraulic_power_kw / (
            req.specification.pump_efficiency * req.specification.motor_efficiency
        )

    warnings = list(base.warnings)
    blockers = list(base.blocking_constraints)
    velocity = calc.get("mainline_velocity_m_s")
    if velocity is not None:
        if velocity > 2.0 and "MAINLINE_VELOCITY_HIGH" not in warnings:
            warnings.append("MAINLINE_VELOCITY_ABOVE_PREFERRED_RANGE")
        elif velocity < 0.5:
            warnings.append("MAINLINE_VELOCITY_BELOW_PREFERRED_RANGE")

    infiltration = req.water_demand.soil.infiltration_rate_mm_h
    application_rate = calc.get("application_rate_mm_h")
    split_application = False
    if (
        infiltration is not None
        and application_rate is not None
        and application_rate > infiltration
    ):
        warnings.append("APPLICATION_RATE_EXCEEDS_SOIL_INFILTRATION")
        split_application = True
        explanations.append("SPLIT_IRRIGATION_RECOMMENDED_TO_REDUCE_RUNOFF")

    motor_margin_kw = None
    motor_sufficient = None
    if req.installed_motor_power_kw is not None and input_power_kw is not None:
        motor_margin_kw = req.installed_motor_power_kw - input_power_kw
        motor_sufficient = motor_margin_kw >= 0
        if not motor_sufficient:
            blockers.append("INSTALLED_MOTOR_POWER_INSUFFICIENT")

    critical_quality = {
        "flow": flow_source,
        "soil_moisture": req.water_demand.soil.moisture_quality.value,
        "weather": req.water_demand.weather.forecast_quality.value,
        "water_demand": "operator_declared" if req.water_demand.mode == "manual" else "derived",
    }
    if req.water_demand.mode == "manual":
        assumptions.append("MANUAL_WATER_DEPTH_NOT_VALIDATED_AGAINST_WATER_TRUTH")
    if flow_source == "unknown":
        assumptions.append("RUNTIME_UNAVAILABLE_WITHOUT_FLOW")

    status = (
        QualityStatus.FAIL
        if blockers
        else (QualityStatus.DEGRADED if warnings or assumptions else QualityStatus.PASS)
    )
    calc.update(
        {
            "net_depth_mm": round(net_depth_mm, 4),
            "gross_depth_mm": round(net_depth_mm / req.specification.application_efficiency, 4),
            "net_volume_m3": round(net_depth_mm * req.specification.irrigated_area_ha * 10.0, 3),
            "gross_volume_m3": round(
                net_depth_mm
                / req.specification.application_efficiency
                * req.specification.irrigated_area_ha
                * 10.0,
                3,
            ),
            "minor_fittings_loss_m": round(fittings_loss_m, 4),
            "required_tdh_m": round(tdh_m, 4) if tdh_m is not None else None,
            "required_pressure_bar": round(required_pressure_bar, 4)
            if required_pressure_bar is not None
            else None,
            "hydraulic_power_kw": round(hydraulic_power_kw, 4)
            if hydraulic_power_kw is not None
            else None,
            "required_input_power_kw": round(input_power_kw, 4)
            if input_power_kw is not None
            else None,
            "installed_motor_margin_kw": round(motor_margin_kw, 4)
            if motor_margin_kw is not None
            else None,
        }
    )
    if calc.get("flow_m3_h"):
        calc["runtime_h"] = round(calc["gross_volume_m3"] / calc["flow_m3_h"], 4)

    payload = {
        "request": req.model_dump(mode="json"),
        "status": status.value,
        "calculations": calc,
        "warnings": sorted(set(warnings)),
        "blocking_constraints": sorted(set(blockers)),
        "explanations": explanations,
        "assumptions": assumptions,
        "input_quality": critical_quality,
    }
    return InteractiveIrrigationCalculationResult(
        status=status,
        calculations=calc,
        water_demand={
            "mode": req.water_demand.mode,
            "crop_type": req.water_demand.crop.crop_type,
            "growth_stage": req.water_demand.crop.growth_stage,
            "et0_mm_day": req.water_demand.weather.et0_mm_day,
            "kc": req.water_demand.crop.kc,
            "forecast_days": req.water_demand.weather.forecast_days,
            "effective_rain_mm": req.water_demand.weather.effective_rain_mm,
            "soil_depletion_mm": req.water_demand.soil.depletion_mm,
            "taw_mm": req.water_demand.soil.taw_mm,
            "raw_mm": req.water_demand.soil.raw_mm,
            "net_depth_mm": calc["net_depth_mm"],
            "gross_depth_mm": calc["gross_depth_mm"],
            "gross_volume_m3": calc["gross_volume_m3"],
            "split_application_recommended": split_application,
        },
        hydraulics={
            "flow_source": flow_source,
            "flow_m3_h": calc.get("flow_m3_h"),
            "velocity_m_s": calc.get("mainline_velocity_m_s"),
            "friction_loss_m": calc.get("mainline_friction_loss_m"),
            "minor_fittings_loss_m": calc.get("minor_fittings_loss_m"),
            "elevation_head_m": req.specification.elevation_change_m,
            "terminal_head_m": round(terminal_head_m, 4),
            "safety_margin_m": req.safety_margin_m,
            "required_tdh_m": calc.get("required_tdh_m"),
            "required_pressure_bar": calc.get("required_pressure_bar"),
        },
        pump_energy={
            "hydraulic_power_kw": calc.get("hydraulic_power_kw"),
            "required_input_power_kw": calc.get("required_input_power_kw"),
            "installed_motor_power_kw": req.installed_motor_power_kw,
            "installed_motor_margin_kw": calc.get("installed_motor_margin_kw"),
        },
        feasibility={
            "status": status.value,
            "motor_sufficient": motor_sufficient,
            "split_application_recommended": split_application,
            "execution_authorized": False,
            "result_class": "engineering_estimate",
        },
        warnings=sorted(set(warnings)),
        blocking_constraints=sorted(set(blockers)),
        explanations=explanations,
        assumptions=assumptions,
        input_quality=critical_quality,
        content_digest=_digest(payload),
    )


# ── IRR-X1.8 Reservoir, Booster and Optional Multi-Pivot Network ─────────────
class WellSupplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    well_id: str
    available_flow_m3_h: float = Field(ge=0)
    enabled: bool = True


class ReservoirInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reservoir_id: str
    capacity_m3: float = Field(gt=0)
    current_volume_m3: float = Field(ge=0)
    minimum_operating_volume_m3: float = Field(default=0, ge=0)
    evaporation_loss_m3_h: float = Field(default=0, ge=0)
    seepage_loss_m3_h: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_levels(self) -> ReservoirInput:
        if self.current_volume_m3 > self.capacity_m3:
            raise ValueError("reservoir current volume cannot exceed capacity")
        if self.minimum_operating_volume_m3 > self.current_volume_m3:
            raise ValueError("reservoir minimum operating volume cannot exceed current volume")
        return self


class BoosterPumpInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pump_id: str
    design_flow_m3_h: float = Field(gt=0)
    design_head_m: float | None = Field(default=None, gt=0)
    installed_motor_power_kw: float | None = Field(default=None, gt=0)
    pump_efficiency: float = Field(default=0.78, gt=0, le=1)
    motor_efficiency: float = Field(default=0.92, gt=0, le=1)
    suction_loss_m: float = Field(default=0, ge=0)
    minimum_suction_head_m: float | None = Field(default=None, ge=0)


class HydraulicSegmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segment_id: str
    from_node: str
    to_node: str
    length_m: float = Field(gt=0)
    internal_diameter_mm: float = Field(gt=0)
    hazen_williams_c: float = Field(default=140, gt=0)
    elevation_change_m: float = 0
    minor_loss_m: float = Field(default=0, ge=0)


class PivotMachineInput(BaseModel):
    """Backward-compatible IRR-X1.8 pivot contract."""

    model_config = ConfigDict(extra="forbid")
    pivot_id: str
    name: str
    field_id: str
    enabled: bool = True
    radius_m: float = Field(gt=0)
    operating_arc_deg: float = Field(default=360, gt=0, le=360)
    design_flow_m3_h: float = Field(gt=0)
    required_inlet_pressure_bar: float = Field(ge=0)
    full_revolution_hours: float | None = Field(default=None, gt=0)

    @property
    def irrigated_area_ha(self) -> float:
        return math.pi * self.radius_m**2 * (self.operating_arc_deg / 360.0) / 10000.0


class IrrigationMachineInput(BaseModel):
    """Vendor-neutral terminal irrigation system attached to the hydraulic network."""

    model_config = ConfigDict(extra="forbid")
    machine_id: str
    name: str
    field_id: str
    system_type: IrrigationSystemType
    enabled: bool = True
    design_flow_m3_h: float = Field(gt=0)
    required_inlet_pressure_bar: float = Field(ge=0)

    # Pivot / linear / reel geometry
    radius_m: float | None = Field(default=None, gt=0)
    operating_arc_deg: float | None = Field(default=None, gt=0, le=360)
    machine_length_m: float | None = Field(default=None, gt=0)
    travel_length_m: float | None = Field(default=None, gt=0)
    hose_length_m: float | None = Field(default=None, gt=0)
    hose_internal_diameter_mm: float | None = Field(default=None, gt=0)

    # Drip / sprinkler / valve-network parameters
    zone_count: int | None = Field(default=None, ge=1)
    concurrent_zones: int | None = Field(default=None, ge=1)
    emitter_count: int | None = Field(default=None, ge=1)
    emitter_flow_lph: float | None = Field(default=None, gt=0)
    sprinkler_count: int | None = Field(default=None, ge=1)
    sprinkler_flow_m3_h: float | None = Field(default=None, gt=0)
    wetted_area_ha: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_system_specific_fields(self) -> IrrigationMachineInput:
        if self.system_type == IrrigationSystemType.CENTER_PIVOT and self.radius_m is None:
            raise ValueError("radius_m is required for center_pivot")
        if self.system_type == IrrigationSystemType.LINEAR_MOVE and self.machine_length_m is None:
            raise ValueError("machine_length_m is required for linear_move")
        if self.system_type == IrrigationSystemType.REEL and self.hose_length_m is None:
            raise ValueError("hose_length_m is required for reel")
        if self.system_type == IrrigationSystemType.DRIP:
            if self.zone_count is None or self.concurrent_zones is None:
                raise ValueError("zone_count and concurrent_zones are required for drip")
            if self.concurrent_zones > self.zone_count:
                raise ValueError("concurrent_zones cannot exceed zone_count")
        if self.system_type == IrrigationSystemType.SPRINKLER and self.sprinkler_count is None:
            raise ValueError("sprinkler_count is required for sprinkler")
        if self.system_type == IrrigationSystemType.VALVE_NETWORK:
            if self.zone_count is None or self.concurrent_zones is None:
                raise ValueError("zone_count and concurrent_zones are required for valve_network")
            if self.concurrent_zones > self.zone_count:
                raise ValueError("concurrent_zones cannot exceed zone_count")
        return self

    @property
    def irrigated_area_ha(self) -> float | None:
        if self.system_type == IrrigationSystemType.CENTER_PIVOT and self.radius_m:
            arc = self.operating_arc_deg or 360.0
            return math.pi * self.radius_m**2 * (arc / 360.0) / 10000.0
        return self.wetted_area_ha


class ReservoirBoosterNetworkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    field_id: str
    season_id: str | None = None
    required_gross_volume_m3: float = Field(gt=0)
    wells: list[WellSupplyInput] = Field(default_factory=list)
    reservoir: ReservoirInput
    booster: BoosterPumpInput
    segments: list[HydraulicSegmentInput] = Field(min_length=1)
    # IRR-X1.9 canonical contract. Empty means pump-only/network-only.
    irrigation_machines: list[IrrigationMachineInput] = Field(default_factory=list)
    requested_machine_ids: list[str] = Field(default_factory=list)
    # IRR-X1.8 compatibility aliases retained for old clients.
    pivots: list[PivotMachineInput] = Field(default_factory=list)
    requested_pivot_ids: list[str] = Field(default_factory=list)
    safety_margin_m: float = Field(default=5, ge=0, le=100)

    @model_validator(mode="after")
    def validate_network(self) -> ReservoirBoosterNetworkRequest:
        machine_ids = {m.machine_id for m in self.irrigation_machines}
        unknown_machines = set(self.requested_machine_ids) - machine_ids
        if unknown_machines:
            raise ValueError(f"unknown requested machine ids: {sorted(unknown_machines)}")
        pivot_ids = {p.pivot_id for p in self.pivots}
        unknown_pivots = set(self.requested_pivot_ids) - pivot_ids
        if unknown_pivots:
            raise ValueError(f"unknown requested pivot ids: {sorted(unknown_pivots)}")
        if self.irrigation_machines and self.pivots:
            raise ValueError("use irrigation_machines or legacy pivots, not both")
        return self


class ReservoirBoosterNetworkResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: QualityStatus
    machine_mode: str
    selected_machines: list[dict[str, Any]]
    # Backward-compatible IRR-X1.8 result aliases.
    pivot_mode: str
    selected_pivots: list[dict[str, Any]]
    reservoir_balance: dict[str, Any]
    booster: dict[str, Any]
    segments: list[dict[str, Any]]
    scenarios: list[dict[str, Any]]
    warnings: list[str]
    blocking_constraints: list[str]
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def _segment_hazen_loss_m(flow_m3_h: float, segment: HydraulicSegmentInput) -> tuple[float, float]:
    q_m3_s = flow_m3_h / 3600.0
    d_m = segment.internal_diameter_mm / 1000.0
    area = math.pi * d_m**2 / 4.0
    velocity = q_m3_s / area
    friction = (
        10.67 * segment.length_m * q_m3_s**1.852 / (segment.hazen_williams_c**1.852 * d_m**4.87)
    )
    total = friction + segment.minor_loss_m + segment.elevation_change_m
    return velocity, total


def _legacy_pivot_as_machine(pivot: PivotMachineInput) -> IrrigationMachineInput:
    return IrrigationMachineInput(
        machine_id=pivot.pivot_id,
        name=pivot.name,
        field_id=pivot.field_id,
        system_type=IrrigationSystemType.CENTER_PIVOT,
        enabled=pivot.enabled,
        radius_m=pivot.radius_m,
        operating_arc_deg=pivot.operating_arc_deg,
        design_flow_m3_h=pivot.design_flow_m3_h,
        required_inlet_pressure_bar=pivot.required_inlet_pressure_bar,
    )


def _machine_metrics(machine: IrrigationMachineInput) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "machine_id": machine.machine_id,
        "name": machine.name,
        "field_id": machine.field_id,
        "system_type": machine.system_type.value,
        "design_flow_m3_h": machine.design_flow_m3_h,
        "required_inlet_pressure_bar": machine.required_inlet_pressure_bar,
        "area_ha": round(machine.irrigated_area_ha, 4) if machine.irrigated_area_ha else None,
    }
    if machine.system_type in {IrrigationSystemType.DRIP, IrrigationSystemType.VALVE_NETWORK}:
        metrics.update(
            {"zone_count": machine.zone_count, "concurrent_zones": machine.concurrent_zones}
        )
    if (
        machine.system_type == IrrigationSystemType.DRIP
        and machine.emitter_count
        and machine.emitter_flow_lph
    ):
        emitter_flow = machine.emitter_count * machine.emitter_flow_lph / 1000.0
        metrics["emitter_aggregate_flow_m3_h"] = round(emitter_flow, 4)
        metrics["declared_vs_emitter_flow_delta_m3_h"] = round(
            machine.design_flow_m3_h - emitter_flow, 4
        )
    if (
        machine.system_type == IrrigationSystemType.SPRINKLER
        and machine.sprinkler_count
        and machine.sprinkler_flow_m3_h
    ):
        sprinkler_flow = machine.sprinkler_count * machine.sprinkler_flow_m3_h
        metrics["sprinkler_aggregate_flow_m3_h"] = round(sprinkler_flow, 4)
        metrics["declared_vs_sprinkler_flow_delta_m3_h"] = round(
            machine.design_flow_m3_h - sprinkler_flow, 4
        )
    if machine.system_type == IrrigationSystemType.REEL:
        metrics.update(
            {
                "hose_length_m": machine.hose_length_m,
                "hose_internal_diameter_mm": machine.hose_internal_diameter_mm,
            }
        )
    if machine.system_type == IrrigationSystemType.LINEAR_MOVE:
        metrics.update(
            {
                "machine_length_m": machine.machine_length_m,
                "travel_length_m": machine.travel_length_m,
            }
        )
    return metrics


def calculate_reservoir_booster_network(
    req: ReservoirBoosterNetworkRequest,
) -> ReservoirBoosterNetworkResult:
    machines = list(req.irrigation_machines)
    legacy_mode = False
    if not machines and req.pivots:
        machines = [_legacy_pivot_as_machine(p) for p in req.pivots]
        legacy_mode = True
    enabled = [m for m in machines if m.enabled]
    requested_ids = req.requested_machine_ids or (req.requested_pivot_ids if legacy_mode else [])
    selected = [m for m in enabled if m.machine_id in requested_ids] if requested_ids else []

    machine_mode = "selected" if selected else "none"
    duty_flow_m3_h = (
        sum(m.design_flow_m3_h for m in selected) if selected else req.booster.design_flow_m3_h
    )
    terminal_head_m = max(
        (m.required_inlet_pressure_bar * 10.19716213 for m in selected), default=0.0
    )

    segment_results: list[dict[str, Any]] = []
    network_head_m = 0.0
    warnings: list[str] = []
    blockers: list[str] = []
    for segment in req.segments:
        velocity, loss = _segment_hazen_loss_m(duty_flow_m3_h, segment)
        network_head_m += loss
        if velocity > 2.0:
            warnings.append(f"SEGMENT_VELOCITY_HIGH:{segment.segment_id}")
        if velocity < 0.5:
            warnings.append(f"SEGMENT_VELOCITY_LOW:{segment.segment_id}")
        segment_results.append(
            {
                "segment_id": segment.segment_id,
                "from_node": segment.from_node,
                "to_node": segment.to_node,
                "flow_m3_h": round(duty_flow_m3_h, 4),
                "velocity_m_s": round(velocity, 4),
                "head_change_m": round(loss, 4),
                "pressure_drop_bar": round(loss / 10.19716213, 4),
            }
        )

    # System-specific consistency checks are advisory unless they invalidate declared capacity.
    for machine in selected:
        if (
            machine.system_type == IrrigationSystemType.DRIP
            and machine.emitter_count
            and machine.emitter_flow_lph
        ):
            aggregate = machine.emitter_count * machine.emitter_flow_lph / 1000.0
            if abs(aggregate - machine.design_flow_m3_h) / machine.design_flow_m3_h > 0.15:
                warnings.append(f"DRIP_EMITTER_FLOW_MISMATCH:{machine.machine_id}")
        if (
            machine.system_type == IrrigationSystemType.SPRINKLER
            and machine.sprinkler_count
            and machine.sprinkler_flow_m3_h
        ):
            aggregate = machine.sprinkler_count * machine.sprinkler_flow_m3_h
            if abs(aggregate - machine.design_flow_m3_h) / machine.design_flow_m3_h > 0.15:
                warnings.append(f"SPRINKLER_FLOW_MISMATCH:{machine.machine_id}")
        if (
            machine.system_type == IrrigationSystemType.REEL
            and machine.hose_internal_diameter_mm is None
        ):
            warnings.append(f"REEL_HOSE_DIAMETER_UNKNOWN:{machine.machine_id}")

    required_head_m = max(
        req.booster.suction_loss_m + network_head_m + terminal_head_m + req.safety_margin_m, 0.0
    )
    hydraulic_power_kw = 9.80665 * (duty_flow_m3_h / 3600.0) * required_head_m
    input_power_kw = hydraulic_power_kw / (
        req.booster.pump_efficiency * req.booster.motor_efficiency
    )
    if duty_flow_m3_h > req.booster.design_flow_m3_h + 1e-9:
        blockers.append("BOOSTER_DESIGN_FLOW_EXCEEDED")
    if req.booster.design_head_m is not None and required_head_m > req.booster.design_head_m + 1e-9:
        blockers.append("BOOSTER_DESIGN_HEAD_EXCEEDED")
    if (
        req.booster.installed_motor_power_kw is not None
        and input_power_kw > req.booster.installed_motor_power_kw + 1e-9
    ):
        blockers.append("BOOSTER_MOTOR_POWER_INSUFFICIENT")

    well_inflow = sum(w.available_flow_m3_h for w in req.wells if w.enabled)
    passive_losses = req.reservoir.evaporation_loss_m3_h + req.reservoir.seepage_loss_m3_h
    net_change_m3_h = well_inflow - duty_flow_m3_h - passive_losses
    usable_volume = req.reservoir.current_volume_m3 - req.reservoir.minimum_operating_volume_m3
    hours_to_min = (
        None
        if net_change_m3_h >= 0
        else usable_volume / abs(net_change_m3_h)
        if usable_volume > 0
        else 0.0
    )
    runtime_h = req.required_gross_volume_m3 / duty_flow_m3_h
    if hours_to_min is not None and runtime_h > hours_to_min + 1e-9:
        blockers.append("RESERVOIR_VOLUME_INSUFFICIENT_FOR_REQUESTED_RUNTIME")
    if req.reservoir.current_volume_m3 <= req.reservoir.minimum_operating_volume_m3:
        blockers.append("RESERVOIR_AT_OR_BELOW_MINIMUM_LEVEL")

    scenarios: list[dict[str, Any]] = []
    for machine in enabled:
        scenarios.append(
            {
                "scenario": f"machine:{machine.machine_id}",
                "machine_ids": [machine.machine_id],
                "system_types": [machine.system_type.value],
                "combined_flow_m3_h": machine.design_flow_m3_h,
                "booster_flow_ok": machine.design_flow_m3_h <= req.booster.design_flow_m3_h,
            }
        )
    if len(enabled) > 1:
        combined = sum(m.design_flow_m3_h for m in enabled)
        scenarios.append(
            {
                "scenario": "all_enabled_machines",
                "machine_ids": [m.machine_id for m in enabled],
                "system_types": [m.system_type.value for m in enabled],
                "combined_flow_m3_h": combined,
                "booster_flow_ok": combined <= req.booster.design_flow_m3_h,
            }
        )

    status = (
        QualityStatus.FAIL
        if blockers
        else (QualityStatus.DEGRADED if warnings else QualityStatus.PASS)
    )
    selected_payload = [_machine_metrics(m) for m in selected]
    selected_pivots = [
        m for m in selected_payload if m["system_type"] == IrrigationSystemType.CENTER_PIVOT.value
    ]
    payload = {
        "tenant_id": req.tenant_id,
        "field_id": req.field_id,
        "season_id": req.season_id,
        "machine_mode": machine_mode,
        "selected_machine_ids": [m.machine_id for m in selected],
        "selected_system_types": [m.system_type.value for m in selected],
        "duty_flow_m3_h": duty_flow_m3_h,
        "required_head_m": required_head_m,
        "reservoir_net_change_m3_h": net_change_m3_h,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
    }
    return ReservoirBoosterNetworkResult(
        status=status,
        machine_mode=machine_mode,
        selected_machines=selected_payload,
        pivot_mode="selected" if selected_pivots else "none",
        selected_pivots=selected_pivots,
        reservoir_balance={
            "well_inflow_m3_h": round(well_inflow, 4),
            "booster_outflow_m3_h": round(duty_flow_m3_h, 4),
            "passive_losses_m3_h": round(passive_losses, 4),
            "net_change_m3_h": round(net_change_m3_h, 4),
            "usable_volume_m3": round(usable_volume, 4),
            "hours_to_minimum": None if hours_to_min is None else round(hours_to_min, 4),
            "requested_runtime_h": round(runtime_h, 4),
        },
        booster={
            "required_flow_m3_h": round(duty_flow_m3_h, 4),
            "required_head_m": round(required_head_m, 4),
            "required_pressure_bar": round(required_head_m / 10.19716213, 4),
            "hydraulic_power_kw": round(hydraulic_power_kw, 4),
            "input_power_kw": round(input_power_kw, 4),
            "design_flow_m3_h": req.booster.design_flow_m3_h,
            "design_head_m": req.booster.design_head_m,
            "installed_motor_power_kw": req.booster.installed_motor_power_kw,
        },
        segments=segment_results,
        scenarios=scenarios,
        warnings=sorted(set(warnings)),
        blocking_constraints=sorted(set(blockers)),
        content_digest=_digest(payload),
    )
