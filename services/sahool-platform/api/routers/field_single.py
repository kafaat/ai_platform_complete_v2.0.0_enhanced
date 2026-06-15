"""api/routers/field_single.py — الحالة التشغيليّة الموحّدة للحقل (Field State)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الرمز ``resolve_field_state`` يُستورَد مباشرةً من ``api.field_operational_state``
(نفس الرمز الذي كان main يستورده — نُقل استيراده هنا لإزالة F401 من main بعد
النقل). لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.field_operational_state import resolve_field_state

router = APIRouter()


@router.get("/api/v1/field/operational-state")
def field_operational_state_endpoint(
    field_id: str,
    confidence_level: str | None = None,
    irrigation_delta_pct: float | None = None,
    rain_forecast_mm: float | None = None,
    soil_moisture_ratio: float | None = None,
    et0_mm: float | None = None,
    ndvi_age_days: float | None = None,
    soil_age_days: float | None = None,
    weather_age_hours: float | None = None,
):
    """يركّب النضارة + الثقة + التناقض في حالة تشغيليّة واحدة رسميّة.

    يُرجع: validity (valid/degraded/conflicted/insufficient) + نمط التنفيذ
    (auto/human_review/blocked) + الأسباب. تركيب شفّاف للمكوّنات الموجودة.
    """
    return resolve_field_state(
        field_id,
        confidence_level,
        irrigation_delta_pct,
        rain_forecast_mm,
        soil_moisture_ratio,
        et0_mm,
        ndvi_age_days,
        soil_age_days,
        weather_age_hours,
    ).to_dict()
