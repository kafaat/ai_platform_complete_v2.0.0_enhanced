"""api/routers/planting.py — تقويم مواعيد الزراعة (Planting Calendar)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

نوافذ + تحذيرات التبكير/التأخير. ``check_planting_date``/``planting_window``/
``supported_crops`` تُستورَد مباشرةً من ``api.planting_calendar`` (نفس الكائنات التي
كان ``main`` يستوردها — نُقل الاستيراد هنا لإزالة F401 من ``main`` بعد نقل الدوالّ).
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.planting_calendar import (
    check_planting_date,
    planting_window,
)
from api.planting_calendar import (
    supported_crops as planting_crops,
)

router = APIRouter()


@router.get("/api/v1/planting/crops")
def planting_crops_endpoint():
    """المحاصيل المدعومة بتقويم مواعيد الزراعة."""
    return {"crops": planting_crops()}


@router.get("/api/v1/planting/window")
def planting_window_endpoint(crop: str = "wheat"):
    """نافذة الزراعة المثلى لمحصول + مخاطر التبكير/التأخير + الحصاد."""
    return planting_window(crop)


@router.get("/api/v1/planting/check")
def planting_check_endpoint(crop: str, month: int):
    """يقيّم: هل الشهر مناسب لزراعة هذا المحصول؟ (1-12)"""
    return check_planting_date(crop, month)
