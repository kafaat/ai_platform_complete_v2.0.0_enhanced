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

from fastapi import APIRouter

from api.weather_analytics import analyze_weather_log, seasonal_planting_guide

router = APIRouter()


@router.post("/api/v1/weather-analytics/analyze")
def weather_analyze_endpoint(records: list[dict]):
    """يحلّل سجلّ طقس يومي → إجهاد حراري + ET0 محسوب + عجز مائي + توصية."""
    return analyze_weather_log(records)


@router.post("/api/v1/weather-analytics/planting-guide")
def weather_planting_guide_endpoint(records: list[dict]):
    """دليل المواسم من السجلّ: متى الزراعة الأمثل ومتى الإجهاد."""
    return seasonal_planting_guide(records)
