"""api/routers/high_value_crops.py — محاصيل عالية القيمة (High-Value Crops)
==========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّتان حرفيّاً مع تغيير ``@app`` إلى ``@router``.

فرص دخول مبكر قليلة الانتشار. ``high_value_crop_detail``/``list_high_value_crops``
تُستورَدان مباشرةً من ``api.high_value_crops`` (نفس الكائنين اللذين كان ``main``
يستوردهما — نُقل الاستيراد هنا لإزالة F401 من ``main`` بعد نقل الدالّتين). لتفادي
الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.high_value_crops import high_value_crop_detail, list_high_value_crops

router = APIRouter()


@router.get("/api/v1/high-value-crops/list")
def high_value_crops_list_endpoint(tier: str | None = None):
    """محاصيل عالية القيمة مصنّفة بصدق حسب ملاءمة الجوف (مثبتة/بحذر/غير مناسبة)."""
    return list_high_value_crops(tier)


@router.get("/api/v1/high-value-crops/detail")
def high_value_crops_detail_endpoint(crop_ar: str):
    """تفصيل محصول عالي القيمة (جوجوبا/مورينجا/ألوفيرا/كينوا...)."""
    return high_value_crop_detail(crop_ar)
