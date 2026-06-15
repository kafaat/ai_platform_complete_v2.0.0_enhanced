"""api/routers/agricultural_proverbs.py — الأمثال الزراعيّة (Agricultural Proverbs)
================================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/agricultural-proverbs/for-date")
def agricultural_proverbs_for_date(date_iso: str, governorate: str | None = None):
    """أمثال التاريخ: تاريخ → المنزلة النشطة → أمثالها (الحلقة المكتملة)."""
    from api.agricultural_proverbs import proverbs_for_date

    return proverbs_for_date(date_iso, governorate=governorate)


@router.get("/api/v1/agricultural-proverbs")
def agricultural_proverbs(marker: str | None = None, governorate: str | None = None):
    """أمثال زراعيّة موثّقة تجسر ثقة المزارع — عرض فقط، مفهرسة بالمعلم/المنطقة."""
    from api.agricultural_proverbs import get_proverbs

    return get_proverbs(marker=marker, governorate=governorate)
