"""api/routers/postharvest.py — ما بعد الحصاد (Post-Harvest Storage)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان في
``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``. لا
تبعيّة مصادقة (عرض إرشادي).

الدوالّ النقيّة (``api.postharvest_advisor``) تُستورَد مباشرةً من وحدتها — وهي نفس
الكائنات التي كانت في ``main`` (لا تُبقى استيراداً يتيماً هناك). لتفادي الاستيراد
الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.postharvest_advisor import (
    check_storage_moisture,
    storage_best_practices,
    storage_pests,
)

router = APIRouter()


@router.get("/api/v1/postharvest/moisture-check")
def postharvest_moisture_endpoint(crop: str, moisture_pct: float):
    """يقيّم: هل رطوبة الحبوب آمنة للتخزين؟ (القمح ≤12%، الذرة ≤13%)"""
    return check_storage_moisture(crop, moisture_pct)


@router.get("/api/v1/postharvest/pests")
def postharvest_pests_endpoint():
    """الآفات المخزنيّة الرئيسيّة للحبوب (سوسة الأرز، الخابرا...)."""
    return storage_pests()


@router.get("/api/v1/postharvest/best-practices")
def postharvest_practices_endpoint(crop: str | None = None):
    """أفضل ممارسات التخزين لتقليل الفقد بعد الحصاد."""
    return storage_best_practices(crop)
