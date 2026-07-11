from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CropIntelligenceInput:
    crop: str | None
    gdd_cumulative: float | None
    gdd_to_maturity: float | None
    phenology_method: str | None = None
    phenology_formula_version: str | None = None
    water_state: dict[str, Any] | None = None
    nutrient_state: dict[str, Any] | None = None
    vegetation_state: dict[str, Any] | None = None
    spectral_state: dict[str, Any] | None = None
    weather_state: dict[str, Any] | None = None
    soil_state: dict[str, Any] | None = None
    biomass_state: dict[str, Any] | None = None
    yield_state: dict[str, Any] | None = None
    root_policy: dict[str, Any] | None = None
    stress_history: list[dict[str, Any]] | None = None
    stress_memory_as_of: str | None = None
    stress_memory_policy: dict[str, Any] | None = None
    prior_stress_memory: dict[str, Any] | None = None
    crop_water_policy: dict[str, Any] | None = None
    field_id: str | None = None
    season_id: str | None = None
    source_ids: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
