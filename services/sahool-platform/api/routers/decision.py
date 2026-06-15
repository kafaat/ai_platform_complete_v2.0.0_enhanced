"""api/routers/decision.py — القرار الزراعي المتكامل (Decision Engine)
===================================================================
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

from api.decision_engine import decide_for_location
from api.decision_explainer import explain_decision

router = APIRouter()


@router.get("/api/v1/decision/for-location")
def decision_for_location_endpoint(
    location: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    elevation_m: float | None = None,
    soil_ph: float | None = None,
    soil_ec_dsm: float | None = None,
    area_ha: float | None = None,
):
    """قرار زراعي متكامل: موقع → إقليم → محاصيل → مخاطر → دليل → خطوات."""
    return decide_for_location(location, lat, lon, elevation_m, soil_ph, soil_ec_dsm, area_ha)


@router.get("/api/v1/decision/explain")
def decision_explain_endpoint(
    location: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    elevation_m: float | None = None,
    soil_ph: float | None = None,
    soil_ec_dsm: float | None = None,
    area_ha: float | None = None,
):
    """يفسّر القرار بلغة طبيعيّة. يُرجع prompt جاهزاً لـClaude + بديل offline.

    القرار نفسه من القواعد (شفّاف)؛ الذكاء الاصطناعي يصوغ الشرح فقط.
    الخادم يأخذ prompt_for_server ويستدعي Claude عبر proxy آمن، ثمّ يعيد
    النصّ إلى explain_decision. بلا إنترنت → الشرح من القواعد (offline).
    """
    decision = decide_for_location(location, lat, lon, elevation_m, soil_ph, soil_ec_dsm, area_ha)
    return explain_decision(decision)
