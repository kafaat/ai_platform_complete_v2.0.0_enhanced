"""api/routers/niche_crops.py — منتجات تصديريّة متخصّصة (Niche Export Crops)
===========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّتان حرفيّاً مع تغيير ``@app`` إلى ``@router``.

موجة ثانية: أصماغ/توابل/أصباغ. ``list_niche_crops``/``niche_crop_detail``
تُستورَدان مباشرةً من ``api.niche_export_crops`` (نفس الكائنين اللذين كان ``main``
يستوردهما — نُقل الاستيراد هنا لإزالة F401 من ``main`` بعد نقل الدالّتين). لتفادي
الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.niche_export_crops import list_niche_crops, niche_crop_detail

router = APIRouter()


@router.get("/api/v1/niche-crops/list")
def niche_crops_list_endpoint(category: str | None = None):
    """منتجات تصديريّة متخصّصة عالية القيمة (صمغ عربي/جوار/حبّة سوداء/قرطم...)."""
    return list_niche_crops(category)


@router.get("/api/v1/niche-crops/detail")
def niche_crops_detail_endpoint(crop_ar: str):
    """تفصيل منتج متخصّص محدّد + ميزته اليمنيّة."""
    return niche_crop_detail(crop_ar)
