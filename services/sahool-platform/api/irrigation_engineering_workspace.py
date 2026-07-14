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
