"""api/routers/water_sensitivity.py — حساسيّة المراحل للإجهاد المائي
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الخمس حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الدوالّ النقيّة (``api.crop_water_sensitivity``) تُستورَد مباشرةً من وحدتها — وهي
نفس الكائنات التي كانت تُستورَد في ``main`` (لا تُبقى استيراداً يتيماً هناك). أمّا
التبعيات/النماذج المُعرَّفة في ``main`` (``get_current_user``/``UserSchema`` ونماذج
الطلب) فتبقى هناك وتُستورَد من ``api.main`` حفظاً لـ``_rebuild_pydantic_models``
واستيرادات الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه
في نهايته فقط (بعد تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.crop_water_sensitivity import (
    assess_stress_risk,
    integrated_irrigation_advice,
    supported_crops,
    water_calendar,
    wheat_water_calendar,
)
from api.main import (
    IntegratedAdviceRequest,
    StressRiskRequest,
    UserSchema,
    get_current_user,
)

router = APIRouter()


@router.get("/api/v1/water-sensitivity/crops")
def water_sensitivity_crops():
    """قائمة المحاصيل اليمنيّة المدعومة بحساسيّة المراحل المائيّة."""
    return {"crops": supported_crops()}


@router.get("/api/v1/water-sensitivity/calendar")
def water_sensitivity_calendar(crop: str = "wheat"):
    """التقويم المائي لمحصول: المراحل + حرجيّتها + السياق اليمني.

    المدعوم: wheat, maize, sorghum, millet, barley (أو أسماؤها العربيّة).
    """
    return water_calendar(crop)


@router.get("/api/v1/water-sensitivity/wheat-calendar")
def water_sensitivity_wheat_calendar():
    """(توافق خلفي) التقويم المائي للقمح."""
    return wheat_water_calendar()


@router.post("/api/v1/water-sensitivity/stress-risk")
def water_sensitivity_stress(
    req: StressRiskRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقيّم خطر الإجهاد المائي بناءً على المحصول والمرحلة ونضوب التربة."""
    return assess_stress_risk(req.crop, req.stage_key, req.depletion_pct)


@router.post("/api/v1/water-sensitivity/integrated-advice")
def water_sensitivity_integrated(
    req: IntegratedAdviceRequest,
    user: UserSchema = Depends(get_current_user),
):
    """توصية ريّ متكاملة: تجمع الحساسيّة (متى حرج) + الاحتياج (كم مم) في قرار واحد."""
    return integrated_irrigation_advice(
        req.crop,
        req.stage_key,
        req.depletion_pct,
        req.net_irrigation_mm,
    )
