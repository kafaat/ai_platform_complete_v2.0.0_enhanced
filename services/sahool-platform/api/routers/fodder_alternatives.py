"""api/routers/fodder_alternatives.py — أعلاف موفّرة للماء (Fodder Alternatives)
===============================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

``list_fodder_alternatives`` تُستورَد مباشرةً من ``api.aromatic_fodder_crops``
(نفس الكائن الذي كان ``main`` يستورده — نُقل الاستيراد هنا لإزالة F401 من ``main``
بعد نقل الدالّة؛ ``list_aromatic_crops`` من الوحدة نفسها انتقلت إلى
``routers/aromatic_crops.py``). لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا
الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.aromatic_fodder_crops import list_fodder_alternatives

router = APIRouter()


@router.get("/api/v1/fodder-alternatives/list")
def fodder_alternatives_list_endpoint():
    """أعلاف موفّرة للماء بديلة للبرسيم المستنزف (Blue panic/سورغم...)."""
    return list_fodder_alternatives()
