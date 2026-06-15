"""api/routers/cultural_calendar.py — التقويم الثقافي (Cultural Calendar)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان في
``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``. عرض فقط — لا
يدخل أيّ توصية (وسم صريح) ولا تبعيّة مصادقة.

الدالّة النقيّة (``api.cultural_calendar``) تُستورَد مباشرةً من وحدتها — وهي نفس
الكائن الذي كان في ``main`` (لا تُبقى استيراداً يتيماً هناك). لتفادي الاستيراد
الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.cultural_calendar import get_cultural_calendar

router = APIRouter()


@router.get("/api/v1/cultural-calendar")
def cultural_calendar(governorate: str | None = None):
    """تقويم ثقافي تراثي للعرض فقط — لا يدخل أيّ توصية (وسم صريح)."""
    return get_cultural_calendar(governorate)
