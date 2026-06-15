"""api/routers/astronomical_timing.py — التوقيت الفلكي (Astronomical Timing)
=========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.astronomical_timing import cross_check_with_gdd, get_calendar_stars
from api.main import (
    AstronomicalCrossCheckRequest,
    UserSchema,
    get_current_user,
)

router = APIRouter()


@router.get("/api/v1/astronomical-timing/stars")
def astronomical_stars():
    """نجوم التقويم الزراعي العربي كمرساة موسميّة رصديّة (سهيل، الثريّا)."""
    return get_calendar_stars()


@router.post("/api/v1/astronomical-timing/cross-check")
def astronomical_cross_check(
    req: AstronomicalCrossCheckRequest,
    user: UserSchema = Depends(get_current_user),
):
    """تحقّق متقاطع: المرساة الفلكيّة مقابل مرحلة GDD (اتّفاق=ثقة، اختلاف=تنبيه)."""
    return cross_check_with_gdd(req.current_date, gdd_stage=req.gdd_stage, anchor=req.anchor)
