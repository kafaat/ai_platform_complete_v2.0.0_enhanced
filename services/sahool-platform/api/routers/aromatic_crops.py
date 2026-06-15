"""api/routers/aromatic_crops.py — نباتات عطريّة/زيوت أساسيّة (Aromatic Crops)
=============================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

``list_aromatic_crops`` تُستورَد مباشرةً من ``api.aromatic_fodder_crops`` (نفس
الكائن الذي كان ``main`` يستورده — نُقل الاستيراد هنا لإزالة F401 من ``main`` بعد
نقل الدالّة؛ ``list_fodder_alternatives`` من الوحدة نفسها انتقلت إلى
``routers/fodder_alternatives.py``). لتفادي الاستيراد الدائريّ: ``api.main`` يستورد
هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.aromatic_fodder_crops import list_aromatic_crops

router = APIRouter()


@router.get("/api/v1/aromatic-crops/list")
def aromatic_crops_list_endpoint():
    """نباتات عطريّة/زيوت أساسيّة متحمّلة للجفاف (قيمة عالية لكلّ قطرة ماء)."""
    return list_aromatic_crops()
