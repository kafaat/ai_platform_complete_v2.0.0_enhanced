"""api/routers/water_harvesting.py — حصاد مياه الأمطار (Water Harvesting)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الأربع حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الدوالّ نقيّة (``api.water_harvesting``) وتُستورَد مباشرةً من وحدتها — نفس الكائنات
التي كانت في ``main`` (لا استيراد يتيم هناك). الاستيراد الكسول (upstream-flood) يبقى
كما هو. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط،
فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.water_harvesting import (
    harvest_potential,
    harvesting_methods,
    method_guide,
)

router = APIRouter()


@router.get("/api/v1/water-harvesting/potential")
def water_potential_endpoint(
    catchment_area_m2: float, annual_rain_mm: float, surface: str = "roof"
):
    """يقدّر كميّة مياه الأمطار القابلة للحصاد سنويّاً (لتر/م³)."""
    return harvest_potential(catchment_area_m2, annual_rain_mm, surface)


@router.get("/api/v1/water-harvesting/methods")
def water_methods_endpoint():
    """طرق حصاد المياه المناسبة (مدرّجات/سدود/صهاريج/مصاطب كنتوريّة)."""
    return harvesting_methods()


@router.get("/api/v1/water-harvesting/method-guide")
def water_method_guide_endpoint(method: str):
    """دليل طريقة حصاد مياه محدّدة (الفوائد + الأنسب + التحذير)."""
    return method_guide(method)


@router.get("/api/v1/water-harvesting/upstream-flood")
def water_upstream_flood_endpoint(local_rain_mm: float, catchment_note: str = ""):
    """مورد السيول الواردة من أحواض أعلى (يتجاوز المطر المحلّي)."""
    from api.water_harvesting import upstream_flood_water

    return upstream_flood_water(local_rain_mm, catchment_note)
