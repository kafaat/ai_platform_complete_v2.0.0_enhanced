"""api/routers/sampling.py — مرشد أخذ عيّنات التربة (Sampling Strategy)
======================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

⚠ هذا النطاق هو ``/api/v1/sampling`` فقط (مرشد الاستراتيجيّة العامّ) — منفصل عن
``/api/v1/soil-sampling`` المُدمَج في ``routers/soil_sampling.py``.

الدوالّ النقيّة (``api.zone_sampling``) تُستورَد مباشرةً من وحدتها — وهي نفس الكائنات
التي كانت في ``main`` (لا تُبقى استيراداً يتيماً هناك). أمّا التبعية
``get_current_user``/``UserSchema`` فتبقى في ``main`` وتُستورَد من ``api.main``. لتفادي
الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import (
    UserSchema,
    get_current_user,
)
from api.zone_sampling import recommend_sampling_strategy, sampling_depth_advice

router = APIRouter()


@router.get("/api/v1/sampling/strategy")
async def sampling_strategy(
    area_ha: float,
    has_history: bool = False,
    variability: str = "unknown",
    crop: str | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """يوصي باستراتيجيّة أخذ عيّنات التربة (zone vs grid) + العدد + العمق.

    إرشادي — يوفّر تكلفة التحاليل (zone: 3-6 vs grid: ~عيّنة/هكتار)."""
    strat = recommend_sampling_strategy(area_ha, has_history, variability)
    strat["depth_advice"] = sampling_depth_advice(crop)
    return strat
