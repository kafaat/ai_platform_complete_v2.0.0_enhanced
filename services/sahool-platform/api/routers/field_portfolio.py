"""api/routers/field_portfolio.py — نقطة تحسين محفظة الحقول (#381)

تكشف الطبقة النقيّة optimize_field_portfolio: توزيع ماء/ميزانيّة المزرعة المحدودة
عبر حقول متعدّدة لتعظيم العائد الكلّيّ. الهامش والاحتياج لكلّ حقل **يمرّرهما المستدعي**
(يُحسبان من /crop-twin/decision/profit-aware لكلّ حقل) — لا تُلفَّق هنا.

محفوظ النمط: POST، `Depends(get_current_user)` (يمرّ حارس المصادقة)، نموذج self-contained.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.field_portfolio import FieldInput, optimize_field_portfolio
from api.main import UserSchema, get_current_user

router = APIRouter()


class PortfolioFieldModel(BaseModel):
    field_id: str
    expected_margin: float  # هامش الحقل عند الريّ الكامل (من economic_state)
    water_demand_m3: float  # احتياجه المائيّ الكلّيّ (م³)
    area_ha: float = 1.0


class FieldPortfolioRequest(BaseModel):
    fields: list[PortfolioFieldModel] = Field(default_factory=list)
    total_water_m3: float = 0.0


@router.post("/api/v1/field-portfolio/optimize")
def optimize_portfolio(
    req: FieldPortfolioRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يوزّع ماء المزرعة المحدود عبر الحقول لتعظيم العائد الكلّيّ — جشِع بالإنتاجيّة.

    صدق: الهوامش/الاحتياجات مُمرَّرة (لا مُختلقة)؛ التوزيع الجزئيّ خطّيّ تقريبيّ موسوم
    calibrated=False؛ الحقول غير المموّلة تظهر unmet.
    """
    fields = [
        FieldInput(
            field_id=f.field_id,
            expected_margin=f.expected_margin,
            water_demand_m3=f.water_demand_m3,
            area_ha=f.area_ha,
        )
        for f in req.fields
    ]
    return optimize_field_portfolio(fields, total_water_m3=req.total_water_m3)
