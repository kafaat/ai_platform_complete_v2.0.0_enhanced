"""api/routers/outcome.py — نقطة قياس نتائج القرار (#383)

تكشف الطبقة النقيّة measure_outcome: تقارن المُخطَّط (من القرار/الخطّة) بالمرصود
الميدانيّ ⇒ هل نجح القرار؟ هل انخفض الإجهاد؟ تحقّق الوفر؟ بلغ الإنتاج الهدف؟

محفوظ النمط: POST، `Depends(get_current_user)` (يمرّ حارس المصادقة)، نموذج self-contained.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.main import UserSchema, get_current_user
from api.outcome_measurement import measure_outcome

router = APIRouter()


class OutcomePlanned(BaseModel):
    recommended_irrigation_mm: float | None = None
    predicted_stress_days: int | None = None
    expected_yield_t_ha: float | None = None
    season_budget_mm: float | None = None


class OutcomeActual(BaseModel):
    actual_irrigation_mm: float | None = None
    observed_stress_days: int | None = None
    actual_yield_t_ha: float | None = None
    actual_water_used_mm: float | None = None


class OutcomeRequest(BaseModel):
    field_id: str | None = None
    planned: OutcomePlanned
    actual: OutcomeActual


@router.post("/api/v1/outcome/measure")
def measure_decision_outcome(
    req: OutcomeRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقيس نتيجة قرار سابق مقابل القياس الميدانيّ — نقيّ في جوهره.

    صدق: يُقيِّم فقط المقاييس المتوفّر طرفاها (مُخطَّط + مرصود)؛ الناقص needs_data.
    """
    out = measure_outcome(req.planned.model_dump(), req.actual.model_dump())
    out["field_id"] = req.field_id
    return out
