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


def build_field_twin_from_canonical_state(state: dict[str, Any]) -> FieldTwinState:
    """Project a thin twin view from ``canonical_field_state.v1`` only.

    The twin is deliberately a derived view: it keeps the canonical state digest in
    assumptions/evidence and refuses unversioned client dictionaries.
    """
    if state.get("schema_version") != "canonical_field_state.v1":
        raise ValueError("Field Digital Twin requires canonical_field_state.v1")
    if not state.get("operational_eligible"):
        return FieldTwinState(
            field_id=str(state.get("field_id") or ""),
            current={
                "canonical_state_digest": state.get("state_digest"),
                "season_id": state.get("season_id"),
                "as_of_time": state.get("as_of_time"),
            },
            risks={"canonical_inputs": "unknown"},
            assumptions=list(state.get("limitations") or []),
        )
    water = state.get("water") or {}
    soil = state.get("soil") or {}
    spectral = state.get("spectral") or {}
    weather = state.get("weather") or {}

    # Read the owner schemas as they exist today.  This is a projection only: no
    # weather/soil/spectral fact is recalculated inside the twin.
    spectral_indices = spectral.get("indices") if isinstance(spectral.get("indices"), dict) else {}
    soil_layers = soil.get("layers") if isinstance(soil.get("layers"), list) else []
    first_soil_layer = soil_layers[0] if soil_layers and isinstance(soil_layers[0], dict) else {}
    weather_products = weather.get("products") if isinstance(weather.get("products"), dict) else {}
    current_weather = (
        weather_products.get("current") if isinstance(weather_products.get("current"), dict) else {}
    )
    current = {
        "canonical_state_digest": state.get("state_digest"),
        "canonical_evidence_digests": dict(state.get("evidence_digests") or {}),
        "season_id": state.get("season_id"),
        "as_of_time": state.get("as_of_time"),
        "depletion_mm": water.get("depletion_mm"),
        "taw_mm": water.get("taw_mm"),
        "raw_mm": water.get("raw_mm"),
        "root_depth_m": water.get("root_depth_m"),
        "soil_profile_id": soil.get("profile_id"),
        "soil_texture": (
            soil.get("soil_texture")
            or soil.get("texture_class")
            or first_soil_layer.get("texture_class")
            or first_soil_layer.get("texture")
        ),
        "soil_quality_status": soil.get("quality_status"),
        "ndvi": spectral_indices.get("ndvi")
        if "ndvi" in spectral_indices
        else spectral.get("ndvi"),
        "ndre": spectral_indices.get("ndre")
        if "ndre" in spectral_indices
        else spectral.get("ndre"),
        "ndmi": spectral_indices.get("ndmi")
        if "ndmi" in spectral_indices
        else spectral.get("ndmi"),
        "msi": spectral_indices.get("msi") if "msi" in spectral_indices else spectral.get("msi"),
        "spectral_acquisition_date": spectral.get("acquisition_date"),
        "weather_state_id": weather.get("state_id"),
        "weather_snapshot_id": weather.get("source_snapshot_id"),
        "weather_quality_status": weather.get("quality_status") or weather.get("quality"),
        "temperature_c": current_weather.get("temperature_c"),
        "vpd_kpa": current_weather.get("vpd_kpa"),
    }
    risks: dict[str, TwinRisk] = {}
    dep, taw = current.get("depletion_mm"), current.get("taw_mm")
    if dep is None or taw in (None, 0):
        risks["water_stress"] = "unknown"
    else:
        ratio = float(dep) / float(taw)
        risks["water_stress"] = "high" if ratio >= 0.7 else "medium" if ratio >= 0.4 else "low"
    return FieldTwinState(
        field_id=str(state["field_id"]),
        current=current,
        risks=risks,
        assumptions=[
            "derived_view_of_canonical_field_state",
            "no_execution_authority",
            f"state_digest:{state.get('state_digest')}",
        ],
    )
