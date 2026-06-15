"""api/routers/agro_zones.py — الأقاليم المناخيّة-الزراعيّة (Agro-Climate Zones)
=================================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الستّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

دوالّ نقيّة (لا قاعدة/تبعيات مشتركة): تكشف تصنيف الأقاليم المناخيّة لليمن. تُستورَد
رموز ``api.agro_climate_zones`` مباشرةً من وحدتها — وهي نفس الرموز التي كان main
يستوردها على مستوى الوحدة (نُقل الاستيراد هنا لإزالة F401 من main بعد نقل الدوالّ).
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.agro_climate_zones import (
    identify_zone,
    list_zones,
    suited_for_zone,
    zone_profile,
)

router = APIRouter()


@router.get("/api/v1/agro-zones/list")
def agro_zones_list_endpoint():
    """الأقاليم المناخيّة-الزراعيّة الستّة لليمن مع ملخّصها."""
    return list_zones()


@router.get("/api/v1/agro-zones/profile")
def agro_zone_profile_endpoint(zone: str):
    """الملفّ المناخي-الزراعي الكامل لإقليم (حرارة/مطر/محاصيل/تجنّب)."""
    return zone_profile(zone)


@router.get("/api/v1/agro-zones/identify")
def agro_zone_identify_endpoint(location: str):
    """يحدّد الإقليم المناخي من اسم محافظة/منطقة يمنيّة."""
    return identify_zone(location)


@router.get("/api/v1/agro-zones/suited-crops")
def agro_zone_suited_endpoint(zone: str, irrigated: bool = True):
    """المحاصيل الملائمة لإقليم + ما يُتجنّب + التنبيه المائي."""
    return suited_for_zone(zone, irrigated)


@router.get("/api/v1/agro-zones/by-elevation")
def agro_zone_elevation_endpoint(altitude_m: float, is_western: bool = True):
    """يحدّد الإقليم بالارتفاع — الأصدق مناخيّاً (المناخ دالّة الارتفاع)."""
    from api.agro_climate_zones import zone_by_elevation

    return zone_by_elevation(altitude_m, is_western=is_western)


@router.get("/api/v1/agro-zones/identify-smart")
def agro_zone_identify_smart_endpoint(
    location: str, altitude_m: float | None = None, is_western: bool = True
):
    """تحديد ذكي: للمحافظات متعدّدة الأقاليم (كتعز) يطلب المديريّة/الارتفاع."""
    from api.agro_climate_zones import identify_zone_v2

    return identify_zone_v2(location, altitude_m, is_western)
