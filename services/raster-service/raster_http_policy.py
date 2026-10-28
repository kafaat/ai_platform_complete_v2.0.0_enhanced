"""raster_http_policy.py — سياسة HTTP المشتركة لمسارات بلاطات/مصغّرات الحقل.

مساعد واحد تستدعيه الراوترات بدل تكرار الفحص في كلّ مسار:

* ``validate_xyz`` — حدود XYZ قبل أيّ تفويض/ذاكرة مؤقّتة/CDSE/تصيير (422 عند البطلان).
  الحدود نفسها التي يفرضها ``shared/gis/cog_tile_proxy.fetch_registered_cog_tile``
  (``0 ≤ z ≤ 22``، ``0 ≤ x,y < 2**z``) — و``z`` يُفحَص أوّلاً فلا يُحسَب ``2**z`` لِـz ضخم.
* ``TENANT_PRIVATE_IMAGE_HEADERS`` — بلاطة الحقل بيانات مستأجِر تُفوَّض بالجلسة، ورابطها
  لا يحمل المستأجِر دائماً؛ فلا يُسمَح لمخزن مشترك (CDN/وسيط) بتخزينها (``private``)،
  ويُعلَن ``Vary`` على ترويسات الهويّة كي لا يُعاد تقديم استجابة جلسة لجلسة أخرى.
* ``requested_dates`` — تواريخ ``/timeseries`` الصريحة: إزالة التكرار مع حفظ الترتيب،
  وسقف لعددها (كلّ تاريخ قراءة شبكة COG) يُرفَض تجاوزه بـ422 صريح.
"""

from __future__ import annotations

import os

from fastapi import HTTPException

MAX_TILE_ZOOM = 22

# ترويسات تُحدِّد هويّة الطالب: Bearer · كوكي الجلسة (auth_request في nginx) · رأس
# المستأجِر الموثوق من البوّابة. ``tid`` في الاستعلام جزء من الرابط فهو في مفتاح التخزين أصلاً.
TENANT_PRIVATE_IMAGE_HEADERS: dict[str, str] = {
    "Cache-Control": "private, max-age=3600",
    "Vary": "Authorization, Cookie, X-Tenant-Id",
}

# سقف تواريخ /timeseries الصريحة: سنة يوميّة كاملة (366) تتجاوز أيّ تواتر Sentinel-2/Landsat.
TIMESERIES_MAX_DATES = int(os.getenv("RASTER_TIMESERIES_MAX_DATES", "366"))


def validate_xyz(z: int, x: int, y: int) -> None:
    """يرفض إحداثيّات XYZ خارج شبكة Web Mercator بـ422 قبل أيّ عمل."""
    if not 0 <= z <= MAX_TILE_ZOOM or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(422, "invalid_tile_coordinates")


def requested_dates(raw: str) -> list[str]:
    """تواريخ مفصولة بفواصل → قائمة فريدة بترتيبها؛ تجاوز السقف ⇒ 422 ``too_many_dates``."""
    dates = list(dict.fromkeys(d.strip() for d in raw.split(",") if d.strip()))
    if len(dates) > TIMESERIES_MAX_DATES:
        raise HTTPException(
            422,
            f"too_many_dates: {len(dates)} > {TIMESERIES_MAX_DATES} — قسّم الطلب أو اترك "
            "dates فارغاً لكلّ التواريخ المتاحة",
        )
    return dates
