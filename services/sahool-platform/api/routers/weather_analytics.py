"""api/routers/weather_analytics.py — تحليلات الطقس (Weather Analytics)
====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.main import UserSchema, get_current_user
from api.weather_analytics import analyze_weather_log, seasonal_planting_guide

router = APIRouter()


@router.post("/api/v1/weather-analytics/analyze")
async def weather_analyze_endpoint(
    records: list[dict],
    lat: float = Query(default=16.0, ge=-90, le=90, description="خطّ عرض السجلّ (Ra في المحرّك)"),
    user: UserSchema = Depends(get_current_user),
):
    """يحلّل سجلّ طقس يومي → إجهاد حراري + ET0 (محرّك الطقس) + عجز مائي + توصية.

    ET0 من منتج سلسلة محرّك الطقس (لا نواة محلّيّة). تعذّر المحرّك ⇒ ``analysis_status``
    = ``partial`` (200): يبقى تحليل الحرارة/الصقيع/الرياح/المطر كاملاً وتُوسَم حقول ET0
    غير متاحة صراحةً (``availability``/``unavailable_products``) — لا اختلاق.
    """
    return await analyze_weather_log(records, lat=lat)


@router.post("/api/v1/weather-analytics/planting-guide")
def weather_planting_guide_endpoint(
    records: list[dict], user: UserSchema = Depends(get_current_user)
):
    """دليل المواسم من السجلّ: متى الزراعة الأمثل ومتى الإجهاد."""
    return seasonal_planting_guide(records)
