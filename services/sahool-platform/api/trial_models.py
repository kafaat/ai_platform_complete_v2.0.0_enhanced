"""api/trial_models.py — نماذج طلب التجارب الحقليّة (Trial Analysis)
==================================================================
كتلة مكتفية ذاتيّاً مُستخرَجة من ``api/main.py`` (تفكيك B1، نمط P0).

تحتوي على نموذج كتلة التجربة المتداخل (``TrialBlockInput``) ونموذج طلب التحليل
الإحصائي (``TrialAnalysisRequest``). مكتفية ذاتيّاً: تعتمد فقط على ``pydantic`` +
stdlib، بلا أيّ رمز آخر من ``api.main``. مستهلِكها الوحيد ``api/routers/trials.py``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TrialBlockInput(BaseModel):
    block_number: int
    treatment_yield: float
    control_yield: float


class METObservationInput(BaseModel):
    genotype: str = Field(min_length=1, max_length=120)
    environment_id: str = Field(min_length=1, max_length=160)
    yield_value: float
    replicate: int | None = Field(default=None, ge=1)


class TrialAnalysisRequest(BaseModel):
    blocks: list[TrialBlockInput]
    confidence_level: float = 0.95
    treatment_label_ar: str = "المعالجة الجديدة"
    season_id: str | None = None
    study_id: str | None = None
    trial_id: str | None = None
    met_observations: list[METObservationInput] = Field(default_factory=list)
