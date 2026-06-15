"""api/routers/propagation.py — الإكثار الخضري + اختيار الأصل (Propagation)
=========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان في
``main.py`` — نُقلت الدوالّ الأربع حرفيّاً مع تغيير ``@app`` إلى ``@router``.

دوالّ النطاق (``propagation_advisor``) كانت مُستورَدة على مستوى وحدة ``main``
وتُستخدَم حصريّاً من هذه الـendpoints؛ نُقل استيرادها هنا (من المصدر مباشرةً)
لتفادي استيراد يتيم في ``main`` بعد النقل — لا تغيير سلوكيّ.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.propagation_advisor import (
    crop_propagation,
    propagation_methods,
    rootstock_selection,
)
from api.propagation_advisor import (
    method_guide as propagation_method_guide,
)

router = APIRouter()


@router.get("/api/v1/propagation/methods")
def propagation_methods_endpoint():
    """طرق الإكثار الخضري الخمس (عقل/تطعيم/برعمة/تقسيم/ترقيد)."""
    return propagation_methods()


@router.get("/api/v1/propagation/method-guide")
def propagation_method_guide_endpoint(method: str):
    """دليل طريقة إكثار محدّدة (الأنواع + النصيحة + الأنسب)."""
    return propagation_method_guide(method)


@router.get("/api/v1/propagation/crop")
def propagation_crop_endpoint(crop: str):
    """طريقة الإكثار المناسبة لمحصول/شجرة من بطاقات الإدخال."""
    return crop_propagation(crop)


@router.get("/api/v1/propagation/rootstock")
def propagation_rootstock_endpoint(stress: str = "salinity"):
    """إرشاد اختيار الأصل المقاوم حسب الإجهاد (salinity/drought/disease/dwarfing)."""
    return rootstock_selection(stress)
