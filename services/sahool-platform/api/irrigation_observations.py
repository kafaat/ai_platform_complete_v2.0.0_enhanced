"""Validate human irrigation observations without promoting them to water truth.

This module performs no I/O. A farmer report or inspection is evidence, not a
verified as-applied ledger entry. Meter readings are reported readings; their
calibration, device identity and ownership are outside this input contract.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictFloat, model_validator

Nonnegative = Annotated[StrictFloat, Field(ge=0)]
Positive = Annotated[StrictFloat, Field(gt=0)]
FUTURE_SKEW_SECONDS = 60


class IrrigationObservationInput(BaseModel):
    """One immutable report about an execution, using exactly one quantity basis.

    ``duration_minutes`` is elapsed duration including interruptions. Estimated
    water uses the remaining pumping duration. Area is the area actually
    irrigated, never the whole field's area or a task-completion percentage.
    Authorization and execution ownership must be checked by the caller.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    observation_id: UUID
    execution_id: UUID
    source: Literal["farmer_task", "field_inspection"]
    outcome: Literal["irrigated", "not_irrigated", "unknown"]
    occurred_at: AwareDatetime
    quantity_method: Literal["meter", "estimated_flow", "declared_volume", "unknown"]
    meter_start_m3: Nonnegative | None = None
    meter_end_m3: Nonnegative | None = None
    flow_m3_h: Positive | None = None
    duration_minutes: Positive | None = None
    volume_m3: Nonnegative | None = None
    irrigated_area_ha: Positive | None = None
    interruptions_minutes: Nonnegative = 0.0
    notes: Annotated[str, Field(strict=True, max_length=2000)] | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> IrrigationObservationInput:
        if self.occurred_at > datetime.now(UTC) + timedelta(seconds=FUTURE_SKEW_SECONDS):
            raise ValueError("occurred_at cannot be in the future")

        evidence = {
            "meter_start_m3": self.meter_start_m3,
            "meter_end_m3": self.meter_end_m3,
            "flow_m3_h": self.flow_m3_h,
            "duration_minutes": self.duration_minutes,
            "volume_m3": self.volume_m3,
        }
        present = {name for name, value in evidence.items() if value is not None}
        required = {
            "meter": {"meter_start_m3", "meter_end_m3"},
            "estimated_flow": {"flow_m3_h", "duration_minutes"},
            "declared_volume": {"volume_m3"},
            "unknown": set(),
        }[self.quantity_method]
        if present != required:
            raise ValueError("quantity evidence must match quantity_method exactly")
        if self.outcome != "irrigated":
            if self.quantity_method != "unknown" or self.irrigated_area_ha is not None:
                raise ValueError("unknown/not_irrigated cannot carry quantity evidence")
        if self.quantity_method != "estimated_flow" and self.interruptions_minutes != 0:
            raise ValueError("interruptions require estimated_flow duration")
        if self.quantity_method == "estimated_flow":
            assert self.duration_minutes is not None
            if self.interruptions_minutes >= self.duration_minutes:
                raise ValueError("interruptions must be less than elapsed duration")
        if self.quantity_method == "meter":
            assert self.meter_start_m3 is not None and self.meter_end_m3 is not None
            if self.meter_end_m3 < self.meter_start_m3:
                raise ValueError("meter regression requires reconciliation, not negative water")

        # Finite inputs can still overflow during multiplication or division.
        quantity = self.computed_quantity()
        if any(
            value is not None and not math.isfinite(value)
            for value in (quantity["volume_m3"], quantity["depth_mm"])
        ):
            raise ValueError("computed quantity must be finite")
        return self

    def computed_quantity(self) -> dict:
        """Return reported/estimated water; never authorize a ledger write."""
        volume = None
        quality = "unknown"
        if self.outcome == "not_irrigated":
            quality = "reported_not_irrigated"
        elif self.quantity_method == "meter":
            assert self.meter_start_m3 is not None and self.meter_end_m3 is not None
            volume = self.meter_end_m3 - self.meter_start_m3
            quality = "meter_observed"
        elif self.quantity_method == "estimated_flow":
            assert self.flow_m3_h is not None and self.duration_minutes is not None
            volume = self.flow_m3_h * ((self.duration_minutes - self.interruptions_minutes) / 60)
            quality = "estimated_flow"
        elif self.quantity_method == "declared_volume":
            volume = self.volume_m3
            quality = "declared_volume"
        depth = None
        if volume is not None and self.irrigated_area_ha is not None:
            depth = (volume / self.irrigated_area_ha) / 10
        return {
            "volume_m3": volume,
            "depth_mm": depth,
            "quality": quality,
            "ledger_eligible": False,
        }


class TaskIrrigationObservationRequest(BaseModel):
    """Typed extension of the existing observation endpoint; no client actor."""

    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, max_length=100)
    irrigation_observation: IrrigationObservationInput
