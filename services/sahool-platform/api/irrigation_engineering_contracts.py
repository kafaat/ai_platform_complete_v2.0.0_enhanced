"""Canonical M2.1 contracts for irrigation engineering assets.

These contracts are manufacturer-neutral, SI-only, and deliberately separate
``design``, ``commissioned``, and ``live`` truth. They do not carry secrets and
are not execution contracts.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LifecycleState(StrEnum):
    DRAFT = "draft"
    DESIGNED = "designed"
    PROCURED = "procured"
    INSTALLED = "installed"
    COMMISSIONING = "commissioning"
    CERTIFIED = "certified"
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class MachineType(StrEnum):
    CENTER_PIVOT = "center_pivot"
    SECTOR_PIVOT = "sector_pivot"
    LINEAR_MOVE = "linear_move"
    TOWABLE_LINEAR = "towable_linear"
    DITCH_FEED = "ditch_feed"
    HOSE_FEED = "hose_feed"
    SWING_AROUND = "swing_around"
    CORNER_ARM = "corner_arm"
    DRIP = "drip"
    FIXED_SPRINKLER = "fixed_sprinkler"
    OTHER = "other"


class TruthEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    design: dict[str, Any] = Field(default_factory=dict)
    commissioned: dict[str, Any] = Field(default_factory=dict)
    live: dict[str, Any] = Field(default_factory=dict)


class EvidenceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str | None = None
    observed_at: str | None = None
    digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    quality: str = "unknown"


class IrrigationProjectContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    farm_id: str | None = None
    field_id: str | None = None
    season_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    lifecycle_state: LifecycleState = LifecycleState.DRAFT
    schema_version: str = "1.0"
    timezone: str = "Asia/Aden"


class PumpEngineeringContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=200)
    pump_type: str
    rated_flow_lps: float | None = Field(default=None, ge=0)
    rated_head_m: float | None = Field(default=None, ge=0)
    rated_power_kw: float | None = Field(default=None, ge=0)
    pump_efficiency: float | None = Field(default=None, gt=0, le=1)
    motor_efficiency: float | None = Field(default=None, gt=0, le=1)
    curve_points: list[dict[str, float]] = Field(default_factory=list)
    truth: TruthEnvelope = Field(default_factory=TruthEnvelope)
    evidence: EvidenceEnvelope = Field(default_factory=EvidenceEnvelope)


class IrrigationMachineContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    project_id: str
    field_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    machine_type: MachineType
    length_m: float | None = Field(default=None, ge=0)
    design_flow_lps: float | None = Field(default=None, ge=0)
    design_inlet_pressure_bar: float | None = Field(default=None, ge=0)
    full_revolution_hours: float | None = Field(default=None, gt=0)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    truth: TruthEnvelope = Field(default_factory=TruthEnvelope)
    evidence: EvidenceEnvelope = Field(default_factory=EvidenceEnvelope)


class EnergySystemContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    project_id: str
    system_type: str
    pv_capacity_kwp: float | None = Field(default=None, ge=0)
    inverter_continuous_kw: float | None = Field(default=None, ge=0)
    battery_chemistry: str | None = None
    battery_nominal_kwh: float | None = Field(default=None, ge=0)
    battery_usable_kwh: float | None = Field(default=None, ge=0)
    battery_continuous_kw: float | None = Field(default=None, ge=0)
    battery_peak_kw: float | None = Field(default=None, ge=0)
    minimum_soc_percent: float | None = Field(default=None, ge=0, le=100)
    emergency_reserve_percent: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def usable_not_above_nominal(self) -> EnergySystemContract:
        if (
            self.battery_nominal_kwh is not None
            and self.battery_usable_kwh is not None
            and self.battery_usable_kwh > self.battery_nominal_kwh
        ):
            raise ValueError("battery_usable_kwh cannot exceed battery_nominal_kwh")
        return self


class ControllerContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    project_id: str
    provider: str
    protocol: str | None = None
    integration_mode: str = "read_only"
    credential_reference: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> ControllerContract:
        ref = (self.credential_reference or "").lower()
        if any(marker in ref for marker in ("password=", "secret=", "token=")):
            raise ValueError("credential_reference must be an opaque secret-manager reference")
        return self
