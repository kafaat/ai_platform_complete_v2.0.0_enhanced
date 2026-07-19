"""gis_boundaries_read.py — قراءة raster-service لطبقة الحدود المشتركة A7 (A6).

**مشروعيّة القراءة (توثيق شرط المالك):** raster-service يقرأ ``admin_boundaries`` وهو **مرجع مشترك معلَن
القراءة العامّة** (قرار A7: readers=["*"]). هذا **ليس** كسراً لحدود «خدمة تقرأ جدول غيرها» (مرض p4) بل
**أوّل استهلاك لنمط shared-reference** الذي أسّسناه — استهلاك مسموح بالعقد لا تسلّل. raster المرشّح
الطبيعيّ (DB + PostGIS + يملك هندسة الحقول لتركيبها مع الحدود في خريطة A6).

الوحدة تحمل **مطهِّر bbox صرفاً** (أرقام فقط + حدّ أقصى للمساحة — مدخل استعلام PostGIS يستحق حارساً
ضدّ bbox وحشيّ يجرّ الجدول كلّه) + باني استعلام GeoJSON/ST_AsSVG. المطهِّر نقيّ قابل للاختبار بلا قاعدة.
"""

from __future__ import annotations

# سقف مساحة bbox (درجات²) — اليمن ~ 12°×9° ≈ 108؛ نسمح بهامش لكن نرفض «العالم كلّه» (جرّ الجدول).
_MAX_BBOX_AREA_DEG2 = 200.0


def sanitize_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    """يُطهّر ``minx,miny,maxx,maxy`` → رباعيّة floats صالحة، أو None (بلا bbox ⇒ كامل الطبقة).

    fail-closed على المدخل الوحشيّ: غير رقميّ · ترتيب مقلوب · خارج 4326 · مساحة تتجاوز السقف ⇒ ValueError.
    """
    if raw is None or not str(raw).strip():
        return None
    parts = str(raw).split(",")
    if len(parts) != 4:
        raise ValueError("bbox must be 'minx,miny,maxx,maxy'")
    try:
        minx, miny, maxx, maxy = (float(p) for p in parts)
    except (TypeError, ValueError) as exc:
        raise ValueError("bbox components must be numeric") from exc
    for v in (minx, maxx):
        if not (-180.0 <= v <= 180.0):
            raise ValueError("bbox longitude out of range")
    for v in (miny, maxy):
        if not (-90.0 <= v <= 90.0):
            raise ValueError("bbox latitude out of range")
    if not (minx < maxx and miny < maxy):
        raise ValueError("bbox min must be < max")
    if (maxx - minx) * (maxy - miny) > _MAX_BBOX_AREA_DEG2:
        raise ValueError("bbox too large (would drag the whole layer)")  # الحارس ضدّ الوحشيّ
    return minx, miny, maxx, maxy


def admin_boundaries_query(
    level: int, bbox: tuple[float, float, float, float] | None
) -> tuple[str, list]:
    """يبني استعلام GeoJSON للحدود (اختياريّاً مقصوصاً بـbbox عبر GIST/ST_Intersects). يعيد (sql, params)."""
    sql = (
        "SELECT admin_code, admin_name_ar, admin_name_en, parent_code, "
        "ST_AsGeoJSON(geom) AS geojson, ST_AsSVG(geom) AS svg "
        "FROM admin_boundaries WHERE admin_level = $1"
    )
    params: list = [int(level)]
    if bbox is not None:
        # ST_Intersects مع GIST index (gix_admin_boundaries_geom) — قصّ فعّال لا مسح كامل.
        sql += " AND geom && ST_MakeEnvelope($2,$3,$4,$5,4326)"
        params += list(bbox)
    sql += " ORDER BY admin_code"
    return sql, params


def source_provenance_query(level: int) -> str:
    """أحدث سجلّ مرجعيّة للمستوى (للتذييل الذاتيّ الاشتقاق في A6)."""
    return (
        "SELECT source, dataset_version, license_title, license_url, url, retrieved_at "
        "FROM admin_boundaries_source WHERE admin_level = $1 ORDER BY loaded_at DESC LIMIT 1"
    )
