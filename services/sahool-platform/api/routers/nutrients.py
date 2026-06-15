"""api/routers/nutrients.py — قواعد 4R للتربة الكلسيّة (Nutrient 4R Plan)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الدوالّ النقيّة (``api.nutrient_4r``) تُستورَد مباشرةً من وحدتها — وهي نفس الكائنات
التي كانت في ``main`` (لا تُبقى استيراداً يتيماً هناك). أمّا التبعيات/النماذج
المُعرَّفة في ``main`` فتبقى هناك وتُستورَد من ``api.main`` حفظاً
لـ``_rebuild_pydantic_models`` واستيرادات الاختبارات. لتفادي الاستيراد الدائريّ:
``api.main`` يستورد هذا الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import (
    Permission,
    Soil4RRequest,
    UserSchema,
    require_permission,
)
from api.nutrient_4r import SoilContext, full_4r_plan

router = APIRouter()


@router.post("/api/v1/nutrients/4r-plan")
def nutrient_4r_plan(
    req: Soil4RRequest,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_PLAN)),
):
    """خطة تسميد 4R للتربة الكلسيّة (تحجب ما يحتاج تحليلاً)."""
    soil = SoilContext(
        caco3_pct=req.caco3_pct,
        ph=req.ph,
        p_ppm=req.p_ppm,
        fe_ppm=req.fe_ppm,
        zn_ppm=req.zn_ppm,
        om_pct=req.om_pct,
    )
    return {"plan": full_4r_plan(soil, req.nutrients)}
