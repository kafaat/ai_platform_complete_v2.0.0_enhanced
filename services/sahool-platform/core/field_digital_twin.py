"""Deterministic field digital twin primitives.

The twin consumes Canonical Field State style inputs and produces simulations with
explicit assumptions. It does not publish recommendations directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TwinRisk = Literal["low", "medium", "high", "unknown"]


@dataclass(frozen=True)
class FieldTwinState:
    field_id: str
    current: dict[str, Any]
    expected: dict[str, Any] = field(default_factory=dict)
    predicted: dict[str, Any] = field(default_factory=dict)
    risks: dict[str, TwinRisk] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)


def simulate_irrigation(state: FieldTwinState, irrigation_mm: float) -> FieldTwinState:
    soil_moisture = float(state.current.get("soil_moisture_pct", 0) or 0)
    predicted_moisture = min(100.0, soil_moisture + irrigation_mm * 0.8)
    risks = dict(state.risks)
    risks["water_stress"] = (
        "low" if predicted_moisture >= 35 else "medium" if predicted_moisture >= 20 else "high"
    )
    predicted = {
        **state.predicted,
        "soil_moisture_pct_after_irrigation": round(predicted_moisture, 2),
    }
    return FieldTwinState(
        field_id=state.field_id,
        current=state.current,
        expected=state.expected,
        predicted=predicted,
        risks=risks,
        assumptions=[
            *state.assumptions,
            "irrigation efficiency simplified at 0.8 moisture response",
        ],
    )


def simulate_salinity_risk(state: FieldTwinState) -> FieldTwinState:
    soil_ec = state.current.get("soil_ec_ds_m")
    water_ec = state.current.get("water_ec_ds_m")
    risks = dict(state.risks)
    if soil_ec is None and water_ec is None:
        risks["salinity"] = "unknown"
    else:
        max_ec = max(float(soil_ec or 0), float(water_ec or 0))
        risks["salinity"] = "high" if max_ec >= 6 else "medium" if max_ec >= 3 else "low"
    return FieldTwinState(
        state.field_id, state.current, state.expected, state.predicted, risks, state.assumptions
    )
