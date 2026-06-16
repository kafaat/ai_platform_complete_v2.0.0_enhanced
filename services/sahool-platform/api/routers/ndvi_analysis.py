"""api/routers/ndvi_analysis.py — تحليل سلسلة NDVI عند الطلب (NDVI time-series).

نقطة تأخذ *سلسلة* قراءات NDVI يوفّرها العميل (تطبيق الجوّال / تاريخ Sentinel)
وتُرجع تحليل اتجاه/شذوذ/صحّة الغطاء النباتيّ من ``core.ndvi_analysis``. المنصّة
تخزّن أحدث NDVI فقط لكلّ حقل (لا تاريخ على الخادم)، لذا لا قراءة قاعدة بيانات هنا
— السلسلة مُمرَّرة من العميل، و``field_id`` للسياق واتّساق المسار فقط. مُقيَّدة
بالدور (FIELD_VIEW) اتّساقاً مع لوحات الحقل المرجعيّة. دعم قرار صادق (قرينة).
"""

from __future__ import annotations

from core.ndvi_analysis import analyze_ndvi_series
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.main import Permission, UserSchema, require_permission

router = APIRouter()


class NdviReading(BaseModel):
    """قراءة NDVI واحدة من العميل."""

    date: str = Field(description="تاريخ القراءة ISO (YYYY-MM-DD) أو نصّ زمنيّ")
    ndvi: float = Field(description="قيمة NDVI للقراءة")


class NdviAnalysisRequest(BaseModel):
    """جسم الطلب: سلسلة قراءات NDVI مُرتّبة زمنيّاً من العميل."""

    series: list[NdviReading] = Field(description="سلسلة قراءات NDVI (مُرتّبة زمنيّاً)")


@router.post("/api/v1/fields/{field_id}/ndvi-analysis")
async def field_ndvi_analysis(
    field_id: str,
    body: NdviAnalysisRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يحلّل سلسلة NDVI مُمرَّرة من العميل: اتجاه + شذوذ + صحّة الغطاء (قرينة).

    لا قراءة قاعدة بيانات — السلسلة من العميل و``field_id`` للسياق. 422 على سلسلة
    فارغة. التحليل صادق: سلسلة قصيرة/غير صالحة ⇒ insufficient/unknown + note_ar."""
    if not body.series:
        raise HTTPException(status_code=422, detail="سلسلة NDVI فارغة — وفّر قراءة واحدة على الأقلّ")
    raw_series = [item.model_dump() for item in body.series]
    return analyze_ndvi_series(raw_series)
