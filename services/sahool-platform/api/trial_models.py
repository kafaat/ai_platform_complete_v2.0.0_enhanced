"""api/trial_models.py — نماذج طلب التجارب الحقليّة (Trial Analysis)
==================================================================
كتلة مكتفية ذاتيّاً مُستخرَجة من ``api/main.py`` (تفكيك B1، نمط P0).

تحتوي على نموذج كتلة التجربة المتداخل (``TrialBlockInput``) ونموذج طلب التحليل
الإحصائي (``TrialAnalysisRequest``). مكتفية ذاتيّاً: تعتمد فقط على ``pydantic`` +
stdlib، بلا أيّ رمز آخر من ``api.main``. مستهلِكها الوحيد ``api/routers/trials.py``.
"""

from __future__ import annotations

from pydantic import BaseModel


class TrialBlockInput(BaseModel):
    block_number: int
    treatment_yield: float
    control_yield: float


class TrialAnalysisRequest(BaseModel):
    blocks: list[TrialBlockInput]
    confidence_level: float = 0.95
    treatment_label_ar: str = "المعالجة الجديدة"
