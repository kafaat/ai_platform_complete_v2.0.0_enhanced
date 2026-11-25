"""Area-weighted catch-can diagnostics, not certification or irrigation efficiency."""

from __future__ import annotations

import math
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

EvidenceText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]


class CatchCanSample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: EvidenceText
    depth_mm: float = Field(strict=True, ge=0, allow_inf_nan=False)
    represented_area_m2: float = Field(strict=True, gt=0, allow_inf_nan=False)


class UniformitySurvey(BaseModel):
    """Explicit represented areas: equal areas or documented pivot annular areas."""

    model_config = ConfigDict(extra="forbid")
    evidence_ref: EvidenceText
    samples: list[CatchCanSample] = Field(min_length=4, max_length=10000)

    @model_validator(mode="after")
    def unique_sample_ids(self) -> UniformitySurvey:
        if len({sample.sample_id for sample in self.samples}) != len(self.samples):
            raise ValueError("catch-can sample IDs must be unique")
        return self


def calculate_uniformity(survey: UniformitySurvey) -> dict[str, Any]:
    """CU and lowest-area-quartile DU; interpolate the quartile boundary by area.

    The four-sample minimum is a calculation constraint, not a field-test standard.
    Areas must come from the supplied sampling design; no radial weights are inferred.
    The output does not establish compliance, efficiency, or execution eligibility.
    """
    max_area = max(sample.represented_area_m2 for sample in survey.samples)
    max_depth = max(sample.depth_mm for sample in survey.samples)
    scaled_areas = [sample.represented_area_m2 / max_area for sample in survey.samples]
    area_sum = math.fsum(scaled_areas)
    weights = [area / area_sum for area in scaled_areas]
    if any(weight == 0 for weight in weights):
        raise ValueError("catch-can represented areas exceed numeric resolution")
    result: dict[str, Any] = {
        "method": "area_weighted_cu_du_lq.v1",
        "evidence_ref": survey.evidence_ref,
        "input_quality": "operator_supplied_unverified",
        "sample_count": len(survey.samples),
        "status": "not_evaluated",
        "compliance_status": "not_evaluated",
        "mean_depth_mm": 0.0,
        "cu_pct": None,
        "du_low_quarter_pct": None,
        "reason": "zero_application_depth",
    }
    if max_depth == 0:
        return result
    depths = [sample.depth_mm / max_depth for sample in survey.samples]
    if any(sample.depth_mm > 0 and depth == 0 for sample, depth in zip(survey.samples, depths, strict=True)):
        raise ValueError("catch-can depths exceed numeric resolution")
    mean = math.fsum(weight * depth for weight, depth in zip(weights, depths, strict=True))
    if mean == 0:
        raise ValueError("weighted catch-can mean exceeds numeric resolution")
    deviation = math.fsum(
        weight * abs(depth - mean) for weight, depth in zip(weights, depths, strict=True)
    )
    remaining = 0.25
    low_quarter = []
    for depth, weight in sorted(zip(depths, weights, strict=True)):
        taken = min(remaining, weight)
        low_quarter.append(taken * depth)
        remaining -= taken
        if remaining <= 0:
            break
    result.update(
        status="calculated",
        reason=None,
        mean_depth_mm=min(mean, 1.0) * max_depth,
        cu_pct=round(100 * (1 - deviation / mean), 6),
        du_low_quarter_pct=round(100 * ((math.fsum(low_quarter) / 0.25) / mean), 6),
    )
    return result
