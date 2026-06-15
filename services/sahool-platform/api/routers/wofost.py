"""api/routers/wofost.py — دليل تعديل بارامترات WOFOST (WOFOST Crop Params)
==========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّتان حرفيّاً مع تغيير ``@app`` إلى ``@router``.

WOFOST عبر المحاصيل. ``list_supported_crop_types``/``wofost_adaptation_guidance``
تُستورَدان مباشرةً من ``api.wofost_crop_params`` (نفس الكائنين اللذين كان ``main``
يستوردهما — نُقل الاستيراد هنا لإزالة F401 من ``main`` بعد نقل الدالّتين). لتفادي
الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.wofost_crop_params import (
    list_supported_crop_types,
    wofost_adaptation_guidance,
)

router = APIRouter()


@router.get("/api/v1/wofost/crop-types")
def wofost_crop_types_endpoint():
    """أنواع نماذج المحاصيل (حولي/شجرة/خضار/درنيّ) وإطار تعديل كلّ منها."""
    return list_supported_crop_types()


@router.get("/api/v1/wofost/adaptation-guidance")
def wofost_adaptation_endpoint(crop: str):
    """دليل تعديل بارامترات WOFOST لمحصول عن النموذج الأساسي (القمح).

    يُرجع نوع النموذج، نسبة التغيير، البارامترات الرئيسيّة (مع المدى والمصدر)،
    وتحذيرات الحدود — إرشاديّ للمعايرة لا قيم نهائيّة مُعايَرة لليمن.
    """
    return wofost_adaptation_guidance(crop)
