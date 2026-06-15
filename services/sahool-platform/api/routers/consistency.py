"""api/routers/consistency.py — اتّساق القرار الزراعي (Agronomic Consistency)
==========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter

# استيراد مباشر من الوحدة الأصليّة: بعد نقل المعالِجَين لم يبقَ في main.py
# مستخدِم آخر لهذين الرمزين فأصبح استيرادهما هناك يتيماً (F401) — حُلّ بنقل
# الاستيراد إلى الموجِّه من مصدره مباشرةً (api.agronomic_consistency).
from api.agronomic_consistency import (
    check_decision_freshness,
    check_irrigation_consistency,
)

router = APIRouter()


@router.get("/api/v1/consistency/irrigation")
def consistency_irrigation_endpoint(
    irrigation_delta_pct: float | None = None,
    rain_forecast_mm: float | None = None,
    soil_moisture_ratio: float | None = None,
    et0_mm: float | None = None,
    recommendation_confidence: float | None = None,
):
    """يفحص توصية ريّ ضدّ الظروف الحاليّة لكشف التناقضات المنطقيّة.

    مثال: زيادة ريّ + توقّع مطر غزير = تناقض يستوجب مراجعة. يُعلِم لا يحجب.
    """
    return check_irrigation_consistency(
        irrigation_delta_pct,
        rain_forecast_mm,
        soil_moisture_ratio,
        et0_mm,
        recommendation_confidence,
    ).to_dict()


@router.get("/api/v1/consistency/freshness")
def consistency_freshness_endpoint(
    ndvi_age_days: float | None = None,
    soil_age_days: float | None = None,
    weather_age_hours: float | None = None,
):
    """يفحص أعمار البيانات الداخلة في القرار (عتبات: NDVI≤5ي، تربة≤2ي، طقس≤6س)."""
    return check_decision_freshness(ndvi_age_days, soil_age_days, weather_age_hours).to_dict()
