"""api/routers/geo_locate.py — تحديد الإقليم من الإحداثيّات (Geo-Locate)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّتان حرفيّاً مع تغيير ``@app`` إلى ``@router``.

رموز ``api.geo_zone_locator`` (locate_field/locate_and_recommend) تُستورَد مباشرةً
من وحدتها (نفس الرموز التي كان main يستوردها — نُقل استيرادها هنا لإزالة F401 من
main بعد النقل). لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في
نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.geo_zone_locator import locate_and_recommend, locate_field

router = APIRouter()


@router.get("/api/v1/geo-locate/field")
def geo_locate_field_endpoint(lat: float, lon: float, elevation_m: float | None = None):
    """يحدّد المحافظة + الإقليم المناخي + المناخ من إحداثيّات الحقل (GPS)."""
    return locate_field(lat, lon, elevation_m)


@router.get("/api/v1/geo-locate/recommend")
def geo_locate_recommend_endpoint(lat: float, lon: float, elevation_m: float | None = None):
    """تحديد الموقع + توصية مباشرة بالمحاصيل الملائمة (تدفّق كامل)."""
    return locate_and_recommend(lat, lon, elevation_m)
