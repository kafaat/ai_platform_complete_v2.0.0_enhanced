"""api/routers/seed.py — البذور المحسّنة (Seed Selection / Quality)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الخمس حرفيّاً مع تغيير ``@app`` إلى ``@router``.

``seed_selection_criteria``/``evaluate_seed_source`` تُستورَدان مباشرةً من
``api.seed_and_practices`` (نفس الكائنات) — بقيّة الكتلة في ``main`` (الأساليب)
لا تزال مستخدَمةً هناك فلم تُمسّ. نموذج الطلب يبقى في ``main`` ويُستورَد من
``api.main`` حفظاً لـ``_rebuild_pydantic_models`` واستيرادات الاختبارات. الاستيرادات
الكسولة داخل الدوالّ تبقى كما هي. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد
هذا الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.main import SeedSourceRequest
from api.seed_and_practices import (
    evaluate_seed_source,
    seed_selection_criteria,
)

router = APIRouter()


@router.get("/api/v1/seed/criteria")
def seed_criteria_endpoint():
    """معايير اختيار البذور/الأصناف المحسّنة (إطار قرار + توجيه لهيئة البحوث)."""
    return seed_selection_criteria()


@router.post("/api/v1/seed/evaluate-source")
def seed_evaluate_endpoint(req: SeedSourceRequest):
    """يقيّم جودة مصدر بذار (اعتماد + نقاوة + إنبات)."""
    return evaluate_seed_source(req.certified, req.purity_pct, req.germination_pct)


@router.get("/api/v1/seed/germination-rate")
def seed_germination_endpoint(sprouted: int, total: int):
    """يحسب معدّل الإنبات من اختبار عيّنة بسيط (المنبت ÷ الإجمالي)."""
    from api.seed_and_practices import germination_rate

    return germination_rate(sprouted, total)


@router.get("/api/v1/seed/storage-check")
def seed_storage_endpoint(temp_f: float, humidity_pct: float):
    """قاعدة تخزين البذور: حرارة(°ف) + رطوبة% < 100."""
    from api.seed_and_practices import storage_check

    return storage_check(temp_f, humidity_pct)


@router.get("/api/v1/seed/sowing-depth")
def seed_sowing_depth_endpoint(seed_size_mm: float, precision: bool = False):
    """عمق البذر المناسب (~5× حجم البذرة، 2× للدقيقة)."""
    from api.seed_and_practices import sowing_depth

    return sowing_depth(seed_size_mm, precision)
