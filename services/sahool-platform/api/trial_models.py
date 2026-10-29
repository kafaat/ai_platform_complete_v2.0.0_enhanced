"""api/trial_models.py — نماذج طلب التجارب الحقليّة (Trial Analysis)
==================================================================
كتلة مكتفية ذاتيّاً مُستخرَجة من ``api/main.py`` (تفكيك B1، نمط P0).

تحتوي على نموذج كتلة التجربة المتداخل (``TrialBlockInput``) ونموذج طلب التحليل
الإحصائي (``TrialAnalysisRequest``). مكتفية ذاتيّاً: تعتمد فقط على ``pydantic`` +
stdlib، بلا أيّ رمز آخر من ``api.main``. مستهلِكها الوحيد ``api/routers/trials.py``.
"""

from __future__ import annotations

import math
from typing import Annotated, Any, Self

from pydantic import BaseModel, BeforeValidator, Field, model_validator


def _json_safe_numeric_input(value: Any) -> Any:
    # FastAPI includes the rejected input in its validation-error response.
    # Represent invalid JSON numeric values textually so the 422 itself remains
    # serializable; the finite-number field still rejects them below.
    if isinstance(value, bool):
        raise ValueError("Boolean values are not trial measurements or identities")
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


FiniteTrialNumber = Annotated[
    float, Field(allow_inf_nan=False), BeforeValidator(_json_safe_numeric_input)
]
PositiveTrialIdentity = Annotated[
    int, Field(ge=1, strict=True), BeforeValidator(_json_safe_numeric_input)
]


class TrialBlockInput(BaseModel):
    block_number: PositiveTrialIdentity
    treatment_yield: FiniteTrialNumber
    control_yield: FiniteTrialNumber


class METObservationInput(BaseModel):
    genotype: str = Field(min_length=1, max_length=120)
    environment_id: str = Field(min_length=1, max_length=160)
    yield_value: FiniteTrialNumber
    replicate: PositiveTrialIdentity | None = None


class SpatialTrialPlanInput(BaseModel):
    field_geometry: dict
    treatments: list[str] = Field(min_length=2)
    n_blocks: int = Field(ge=3, le=20, strict=True)
    machine_heading_deg: FiniteTrialNumber = Field(ge=0, lt=360)
    implement_width_m: FiniteTrialNumber = Field(gt=0)
    randomization_seed: str = Field(min_length=1, max_length=240)
    headland_m: FiniteTrialNumber = Field(default=0.0, ge=0)
    strip_gap_m: FiniteTrialNumber = Field(default=0.0, ge=0)
    min_plot_area_m2: FiniteTrialNumber = Field(default=20.0, gt=0)


class TrialAnalysisRequest(BaseModel):
    blocks: list[TrialBlockInput]
    confidence_level: FiniteTrialNumber = Field(default=0.95, gt=0, lt=1)
    treatment_label_ar: str = "المعالجة الجديدة"
    season_id: str | None = None
    study_id: str | None = None
    trial_id: str | None = None
    met_observations: list[METObservationInput] = Field(default_factory=list)
    spatial_plan: SpatialTrialPlanInput | None = None

    @model_validator(mode="after")
    def validate_trial_structure(self) -> Self:
        block_ids = [block.block_number for block in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("Duplicate block_number; blocks must be unique")
        if self.trial_id is not None:
            self.trial_id = self.trial_id.strip()
        if self.spatial_plan is not None and (
            not self.trial_id or self.trial_id.casefold() == "unbound-trial"
        ):
            raise ValueError("A nonblank trial_id is required for spatial_plan")
        return self
