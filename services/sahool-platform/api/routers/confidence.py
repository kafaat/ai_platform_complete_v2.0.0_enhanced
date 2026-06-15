"""api/routers/confidence.py — ثقة القراءات والتوصيات (Confidence)
===============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

# استيراد مباشر من الوحدتين الأصليّتين: بعد نقل المعالِجَين لم يبقَ في main.py
# مستخدِم آخر لـ compute_ndvi_confidence/irrigation_confidence فأصبحا يتيمَين
# (F401) — حُلّا بنقل الاستيراد إلى الموجِّه من مصدرهما مباشرةً.
from api.confidence_aggregation import irrigation_confidence
from api.confidence_engine import compute_ndvi_confidence
from api.main import (
    IrrigationConfRequest,
    NdviConfidenceRequest,
    UserSchema,
    _parse_iso_utc,
    get_current_user,
)

router = APIRouter()


@router.post("/api/v1/confidence/ndvi")
def ndvi_confidence(
    req: NdviConfidenceRequest,
    user: UserSchema = Depends(get_current_user),
):
    """ثقة قراءة NDVI: cloud + temporal + coverage + source."""
    obs = _parse_iso_utc(req.observation_date)
    conf = compute_ndvi_confidence(
        ndvi_value=req.ndvi_value,
        observation_date=obs,
        field_area_ha=req.field_area_ha,
        cloud_pct=req.cloud_pct,
        cloud_shadow_pct=req.cloud_shadow_pct,
        cirrus_pct=req.cirrus_pct,
        has_ground_truth=req.has_ground_truth,
    )
    return conf.to_dict()


@router.post("/api/v1/confidence/irrigation")
def irrigation_rec_confidence(
    req: IrrigationConfRequest,
    user: UserSchema = Depends(get_current_user),
):
    """ثقة توصية ري مُجمَّعة — ET0 حرج (غيابه → unsafe)."""
    agg = irrigation_confidence(
        req.ndvi_confidence,
        req.et0_confidence,
        req.soil_moisture_confidence,
        req.weather_forecast_confidence,
    )
    return agg.to_dict()
