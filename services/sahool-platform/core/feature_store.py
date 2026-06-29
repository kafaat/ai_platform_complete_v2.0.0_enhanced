"""Small, in-process feature registry for agronomic models.

The production deployment can replace this with Feast or a managed feature store;
this module defines stable contracts and validation so services do not invent ad
hoc model inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

FeatureFamily = Literal[
    "weather", "satellite", "soil", "water", "iot", "operation", "yield", "economics"
]


class FeatureStoreError(ValueError):
    pass


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    family: FeatureFamily
    unit: str
    required_for: tuple[str, ...] = ()
    source_of_truth: str = "canonical_field_state"

    def __post_init__(self) -> None:
        if self.source_of_truth != "canonical_field_state":
            raise FeatureStoreError("features must be sourced from Canonical Field State")


@dataclass(frozen=True)
class FeatureValue:
    tenant_id: str
    field_id: str
    spec: FeatureSpec
    value: float | int | str | bool | None
    observed_at: str
    confidence: Literal["none", "low", "medium", "high"] = "medium"

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.field_id:
            raise FeatureStoreError("tenant_id and field_id are required")
        try:
            datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FeatureStoreError("observed_at must be ISO-8601") from exc


class FeatureRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, FeatureSpec] = {}

    def register(self, spec: FeatureSpec) -> None:
        if spec.name in self._specs and self._specs[spec.name] != spec:
            raise FeatureStoreError(f"feature spec conflict: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> FeatureSpec:
        if name not in self._specs:
            raise FeatureStoreError(f"unknown feature: {name}")
        return self._specs[name]

    def validate_values(self, values: list[FeatureValue]) -> dict[str, Any]:
        missing_specs = [v.spec.name for v in values if v.spec.name not in self._specs]
        families = sorted({v.spec.family for v in values})
        return {
            "count": len(values),
            "families": families,
            "missing_specs": missing_specs,
            "valid": not missing_specs,
        }


def default_feature_registry() -> FeatureRegistry:
    registry = FeatureRegistry()
    for spec in [
        FeatureSpec("et0_mm", "weather", "mm/day", ("irrigation",)),
        FeatureSpec("wind_speed_m_s", "weather", "m/s", ("spray_window",)),
        FeatureSpec("ndvi", "satellite", "index", ("health",)),
        FeatureSpec("soil_ec_ds_m", "soil", "dS/m", ("salinity", "fertility")),
        FeatureSpec("water_ec_ds_m", "water", "dS/m", ("irrigation",)),
        FeatureSpec("soil_moisture_pct", "iot", "%", ("irrigation",)),
        FeatureSpec("actual_yield_t_ha", "yield", "t/ha", ("learning",)),
    ]:
        registry.register(spec)
    return registry
