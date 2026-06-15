"""api/routers/climate_analogs.py — المناطق المشابهة مناخيّاً (Climate Analogs)
==============================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الخمس حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الدوالّ نقيّة (``api.climate_analogs``) وتُستورَد مباشرةً من وحدتها — نفس الكائنات
التي كانت في ``main`` (لا استيراد يتيم هناك). الاستيرادات الكسولة (strategic-tiers /
strategy) تبقى كما هي. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه
في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.climate_analogs import (
    analog_detail,
    desert_proven_crops,
    list_analog_regions,
)

router = APIRouter()


@router.get("/api/v1/climate-analogs/list")
def climate_analogs_list_endpoint():
    """المناطق العالميّة المشابهة مناخيّاً للصحراء اليمنيّة (الحزم/الجوف)."""
    return list_analog_regions()


@router.get("/api/v1/climate-analogs/detail")
def climate_analogs_detail_endpoint(region: str):
    """تفصيل منطقة مشابهة + دروسها (الجوف السعوديّة/النقب/أريزونا...)."""
    return analog_detail(region)


@router.get("/api/v1/climate-analogs/desert-crops")
def climate_analogs_crops_endpoint(category: str | None = None):
    """المحاصيل المثبتة عالميّاً في المناخ الصحراوي (أشجار/موسميّة/حديثة)."""
    return desert_proven_crops(category)


@router.get("/api/v1/climate-analogs/strategic-tiers")
def climate_analogs_strategic_endpoint(tier: str | None = None):
    """التصنيف الاستراتيجي للمحاصيل الصحراويّة (قيمة × استدامة مائيّة × تصدير)."""
    from api.climate_analogs import strategic_tiers

    return strategic_tiers(tier)


@router.get("/api/v1/climate-analogs/strategy")
def climate_analogs_strategy_endpoint():
    """الاستراتيجيّة المركّبة للجوف (مزيج من المناطق) + اتّجاه Premium Desert Ag."""
    from api.climate_analogs import composite_strategy

    return composite_strategy()
