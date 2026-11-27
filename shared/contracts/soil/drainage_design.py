"""Optional survey evidence for diagnostic drainage and compaction scenarios."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Positive = Annotated[float, Field(gt=0, le=1e7)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]


class SurveyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class DrainSpacingScenario(SurveyModel):
    """Two-layer steady-state Hooghoudt; equivalent depth must be supplied for the design."""

    source_ref: Reference
    k_above_m_day: Positive
    k_below_m_day: Positive
    equivalent_depth_m: Positive
    midpoint_head_m: Positive
    recharge_mm_day: Positive

    @model_validator(mode="after")
    def representable_spacing(self):
        self.assessment()
        return self

    def assessment(self) -> dict:
        h = self.midpoint_head_m
        flux = self.recharge_mm_day / 1000
        if flux == 0:
            raise ValueError("recharge outside numerical range")
        spacing = math.sqrt(
            (8 * self.k_below_m_day * self.equivalent_depth_m * h + 4 * self.k_above_m_day * h * h)
            / flux
        )
        if not math.isfinite(spacing) or spacing <= 0:
            raise ValueError("spacing outside numerical range")
        return {
            "method": "Hooghoudt, steady state",
            "inputs": self.model_dump(),
            "spacing_m": spacing,
            "status": "planning_estimate",
            "equivalent_depth_basis": "supplied_for_candidate_spacing",
        }


class ConeReading(SurveyModel):
    depth_cm: Positive
    resistance_mpa: float = Field(ge=0, le=100)


class CompactionSurvey(SurveyModel):
    source_ref: Reference
    moisture_condition: Literal["field_capacity", "dry", "wet", "unknown"]
    reference_mpa: Positive
    reference_source: Reference
    samples: list[ConeReading] = Field(min_length=1, max_length=250)

    @model_validator(mode="after")
    def unique_depths(self):
        if len({s.depth_cm for s in self.samples}) != len(self.samples):
            raise ValueError("duplicate depth in penetrometer profile")
        return self

    def assessment(self) -> dict:
        depths = None
        if self.moisture_condition == "field_capacity":
            depths = sorted(
                s.depth_cm for s in self.samples if s.resistance_mpa >= self.reference_mpa
            )
        return {
            "inputs": self.model_dump(),
            "exceeding_depths_cm": depths,
            "status": "measured_profile" if depths is not None else "moisture_not_comparable",
        }


class QualityFactor(SurveyModel):
    name: Reference
    unit: Reference
    method: Reference
    observation_ref: Reference | None = None
    observed: float | None = Field(default=None, ge=-1e12, le=1e12)
    zero_score_at: float = Field(ge=-1e12, le=1e12)
    full_score_at: float = Field(ge=-1e12, le=1e12)
    weight: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def valid_endpoints(self):
        if self.zero_score_at == self.full_score_at:
            raise ValueError("quality score endpoints must differ")
        if self.observed is not None and not self.observation_ref:
            raise ValueError("an observed factor needs a source")
        return self


class LandQualityScenario(SurveyModel):
    profile_ref: Reference
    factors: list[QualityFactor] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def normalized_weights(self):
        if len({x.name for x in self.factors}) != len(self.factors) or not math.isclose(
            sum(x.weight for x in self.factors), 1, abs_tol=1e-9
        ):
            raise ValueError("unique factors with weights summing to one are required")
        return self

    def assessment(self):
        scores = {}
        for f in self.factors:
            if f.observed is None:
                scores[f.name] = None
            else:
                raw = (f.observed - f.zero_score_at) / (f.full_score_at - f.zero_score_at)
                scores[f.name] = max(0.0, min(1.0, raw))
        score = (
            None
            if None in scores.values()
            else sum(f.weight * scores[f.name] for f in self.factors)
        )
        return {
            "basis": "user_defined_profile",
            "inputs": self.model_dump(),
            "factor_scores": scores,
            "weighted_index": score,
            "execution_authorized": False,
        }
