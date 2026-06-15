"""api/routers/orchard.py — مخطّط البستان المختلط (Orchard Planner)
===================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّتان حرفيّاً مع تغيير ``@app`` إلى ``@router``.

بستان استثماري (لوز/زيتون/فستق). ``mixed_orchard_plan``/``orchard_economics_note``
تُستورَدان مباشرةً من ``api.orchard_planner`` (نفس الكائنين اللذين كان ``main``
يستوردهما — نُقل الاستيراد هنا لإزالة F401 من ``main`` بعد نقل الدالّتين). لتفادي
الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.orchard_planner import mixed_orchard_plan, orchard_economics_note

router = APIRouter()


@router.get("/api/v1/orchard/plan")
def orchard_plan_endpoint(area_ha: float = 1.0):
    """يخطّط بستاناً مختلطاً صحراويّاً: توزيع + كثافة + جدول عائد زمني."""
    return mixed_orchard_plan(area_ha)


@router.get("/api/v1/orchard/economics")
def orchard_economics_endpoint(area_ha: float = 1.0):
    """ملاحظات اقتصاديّة تقديريّة للبستان المختلط (سيناريو لا وعد)."""
    return orchard_economics_note(area_ha)
