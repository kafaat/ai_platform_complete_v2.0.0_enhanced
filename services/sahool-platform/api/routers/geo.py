"""api/routers/geo.py — الكشف العكسي للموقع (Reverse Geocoding)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

المساعِد ``_reverse_geocode`` يبقى مُعرَّفاً في ``api.main`` (يستخدمه معالِجٌ آخر
هناك أيضاً) ويُستورَد من هنا. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا
الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import (
    Permission,
    UserSchema,
    _reverse_geocode,
    require_permission,
)

router = APIRouter()


@router.get("/api/v1/geo/reverse")
def geo_reverse_endpoint(
    lat: float,
    lon: float,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """كشف عكسي خفيف: مركز الحقل → {country, region} — لعرض الموقع المكتشف آليّاً
    في الواجهة فور رسم المضلّع (قبل الحفظ). دالّة نقيّة (لا قاعدة)."""
    country, region = _reverse_geocode(lat, lon)
    return {"country": country, "region": region}
