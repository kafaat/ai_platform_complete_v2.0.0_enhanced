"""api/routers/regional_calendar.py — التقويم الإقليمي (Regional Calendar)
=========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان في
``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``. لا تبعيّة
مصادقة. الاستيراد الكسول لـ``get_regional_calendar`` يبقى داخل الدالّة كما كان (لا
يتيتّم شيء في ``main``). لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه
في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/regional-calendar")
def regional_calendar(governorate: str | None = None):
    """التقويم الزراعي الإقليمي للمحافظة (حِميري للهضبة، حضرمي للوادي)."""
    from api.astronomical_timing import get_regional_calendar

    return get_regional_calendar(governorate)
