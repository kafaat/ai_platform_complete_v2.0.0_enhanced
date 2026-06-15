"""api/routers/seasonal_risk.py — نوافذ المخاطر المناخيّة الموسميّة (Seasonal Risk)
==================================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

نوافذ المخاطر + ساعات البرودة. ``chill_hours_estimate``/``stage_risk_check``/
``zone_risk_calendar`` تُستورَد مباشرةً من ``api.seasonal_risk`` (نفس الكائنات التي
كان ``main`` يستوردها — نُقل الاستيراد هنا لإزالة F401 من ``main`` بعد نقل الدوالّ).
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.seasonal_risk import (
    chill_hours_estimate,
    stage_risk_check,
    zone_risk_calendar,
)

router = APIRouter()


@router.get("/api/v1/seasonal-risk/calendar")
def seasonal_risk_calendar_endpoint(zone: str):
    """نوافذ المخاطر المناخيّة الموسميّة لإقليم (موجات حرّ/صقيع/مطر حصاد)."""
    return zone_risk_calendar(zone)


@router.get("/api/v1/seasonal-risk/stage-check")
def seasonal_risk_stage_endpoint(zone: str, stage_ar: str):
    """يفحص مخاطر مرحلة نموّ محدّدة في إقليم (مثلاً الإزهار في الجوف)."""
    return stage_risk_check(zone, stage_ar)


@router.get("/api/v1/seasonal-risk/chill-hours")
def seasonal_risk_chill_endpoint(zone: str):
    """يقدّر ساعات البرودة ويقارنها باحتياج الأشجار المتساقطة."""
    return chill_hours_estimate(zone)
