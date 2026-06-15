"""api/routers/practices.py — الأساليب الزراعيّة المحسّنة (Improved Practices)
=============================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّتان حرفيّاً مع تغيير ``@app`` إلى ``@router``.

``practice_guide``/``supported_practices`` تُستورَدان مباشرةً من
``api.seed_and_practices`` (نفس الكائنين اللذين كان ``main`` يستوردهما — نُقل
الاستيراد هنا لإزالة F401 من ``main`` بعد نقل الدالّتين؛ بقيّة الكتلة [البذور] لا
تزال مستخدَمةً في ``main``/``routers/seed.py`` فلم تُمسّ). لتفادي الاستيراد
الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.seed_and_practices import practice_guide, supported_practices

router = APIRouter()


@router.get("/api/v1/practices/list")
def practices_list_endpoint():
    """الأساليب الزراعيّة المحسّنة المدعومة."""
    return {"practices": supported_practices()}


@router.get("/api/v1/practices/guide")
def practices_guide_endpoint(practice: str):
    """دليل أسلوب زراعي محسّن (تحميل/زراعة حافظة/مدرّجات/ريّ تكميلي)."""
    return practice_guide(practice)
