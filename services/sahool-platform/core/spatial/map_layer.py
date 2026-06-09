"""
sahool_core.spatial.map_layer
==============================
جسر العرض الجغرافي — يحوّل ZoneOfInterest وقيم المؤشّرات إلى GeoJSON
معياري جاهز للعرض في Leaflet/Mapbox دون اقتران بمكتبة عرض معيّنة.

الفجوة المسدودة: ZoneOfInterest يحوي geometry وقيمة لكن لا "بطاقة
عرض" معيارية. الواجهة كانت تحتاج تحويلاً يدوياً لكل مؤشّر. هذه
الوحدة تنتج FeatureCollection قياسياً (RFC 7946) يقرأه أي عارض خرائط.

المبادئ المحفوظة:
  • النواة محايدة العارض (لا React/Leaflet/Mapbox في الكود)
  • لا اختراع: المنطقة بلا قيمة قياس → GeoJSON بـvalue=null
  • التصنيف اللوني فئوي (low/medium/high)، لا rainbow وهمي
  • الصدق: properties يحمل سبب الاهتمام صراحةً (للنقر للقراءة)

الاستخدام النموذجي (في الواجهة):
  zones = detect_zones_of_interest(...)
  fc = zones_to_geojson(zones, indicator='ndvi')
  L.geoJSON(fc, {style: styleByValue}).addTo(map)
"""
from __future__ import annotations

from dataclasses import dataclass

# تصنيف الألوان الفئوي (لا rainbow وهمي)
# يطابق مبدأ "الثقة فئة لا نسبة"
_INDICATOR_BANDS = {
    "ndvi": [
        (0.0, 0.2, "low",    "#8B4513", "نباتي ضعيف/أرض عارية"),
        (0.2, 0.4, "medium", "#DAA520", "نباتي متوسّط"),
        (0.4, 0.7, "good",   "#90EE90", "نباتي جيّد"),
        (0.7, 1.0, "high",   "#228B22", "كثيف"),
    ],
    "ndmi": [   # الرطوبة النباتية
        (-1.0, 0.0,  "dry",       "#D2691E", "جفاف نباتي"),
        ( 0.0, 0.2,  "moderate",  "#F4A460", "رطوبة متوسّطة"),
        ( 0.2, 0.4,  "good",      "#87CEEB", "رطوبة جيّدة"),
        ( 0.4, 1.0,  "high",      "#4682B4", "رطوبة مرتفعة"),
    ],
    "salinity_si": [   # مؤشّر الملوحة الطيفي (قرينة سقف منخفض)
        (0.0,  0.1,  "low",      "#90EE90", "ملوحة طيفية منخفضة"),
        (0.1,  0.3,  "moderate", "#FFD700", "ملوحة طيفية متوسّطة — يلزم EC مخبري"),
        (0.3,  1.0,  "high",     "#DC143C", "ملوحة طيفية مرتفعة — يلزم EC مخبري"),
    ],
}


@dataclass
class MapFeatureStyle:
    band_name: str
    color: str
    description_ar: str


def classify_value(indicator: str, value: float | None) -> MapFeatureStyle | None:
    """يصنّف قيمة المؤشّر فئوياً — لا تدرّج وهمي."""
    if value is None:
        return MapFeatureStyle("unknown", "#808080", "قيمة غير متوفّرة")
    bands = _INDICATOR_BANDS.get(indicator)
    if not bands:
        return MapFeatureStyle("unknown", "#808080",
                               f"المؤشّر '{indicator}' غير مصنّف")
    for lo, hi, name, color, desc in bands:
        if lo <= value <= hi:
            return MapFeatureStyle(name, color, desc)
    # خارج النطاق الكلّي (لا اختراع)
    return MapFeatureStyle("out_of_range", "#000000", "خارج النطاق المتوقّع")


def _polygon_to_geojson_coords(polygon: list) -> list:
    """يحوّل قائمة نقاط (lon,lat) إلى تنسيق GeoJSON [[lon,lat],...,[lon,lat]].

    GeoJSON يتطلّب إغلاق الحلقة (النقطة الأولى = الأخيرة)."""
    if not polygon:
        return []
    # نقبل (lon, lat) tuples أو [lon, lat] lists أو dicts
    coords = []
    for pt in polygon:
        if isinstance(pt, dict):
            lon = pt.get("lon") or pt.get("longitude") or pt.get("lng")
            lat = pt.get("lat") or pt.get("latitude")
        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
            lon, lat = pt[0], pt[1]
        else:
            continue
        if lon is not None and lat is not None:
            coords.append([float(lon), float(lat)])
    # إغلاق الحلقة
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def zone_to_feature(zone, *, indicator: str, value: float | None = None,
                    extra_props: dict | None = None) -> dict | None:
    """يحوّل ZoneOfInterest واحد إلى GeoJSON Feature.

    zone يجب أن يكون له .geometry (قائمة نقاط) و(اختياراً) .value و.reason_ar."""
    geom = getattr(zone, "geometry", None) or getattr(zone, "polygon", None)
    if not geom:
        return None
    coords = _polygon_to_geojson_coords(geom)
    if len(coords) < 4:   # GeoJSON Polygon يحتاج ≥3 نقاط + إغلاق
        return None

    val = value if value is not None else getattr(zone, "value", None)
    style = classify_value(indicator, val)

    props = {
        "indicator": indicator,
        "value": val,
        "band": style.band_name if style else "unknown",
        "color": style.color if style else "#808080",
        "description_ar": style.description_ar if style else "غير مصنّف",
        "reason_ar": getattr(zone, "reason_ar", None),
        "zone_id": getattr(zone, "zone_id", None),
        "area_ha": getattr(zone, "area_ha", None),
    }
    # تضمين المعلومات الإضافية (مثل تاريخ القياس، الثقة)
    if extra_props:
        props.update(extra_props)
    # حذف None لتنظيف JSON
    props = {k: v for k, v in props.items() if v is not None}

    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": props,
    }


def zones_to_geojson(zones: list, *, indicator: str,
                     metadata: dict | None = None) -> dict:
    """يحوّل قائمة ZoneOfInterest إلى FeatureCollection معياري.

    النتيجة جاهزة للعرض المباشر في Leaflet (L.geoJSON) أو Mapbox.
    metadata: معلومات إضافية تُحفظ في properties المجموعة (تاريخ القياس،
    اسم الحقل، الثقة الإجمالية)."""
    features = []
    for z in zones:
        f = zone_to_feature(z, indicator=indicator)
        if f:
            features.append(f)

    fc: dict = {
        "type": "FeatureCollection",
        "features": features,
    }
    if metadata:
        # غير معياري لـRFC 7946 لكنه قانوني (top-level extra members مسموح)
        fc["metadata"] = {k: v for k, v in metadata.items() if v is not None}
    return fc


def legend_for_indicator(indicator: str) -> list[dict]:
    """يُرجع وسيلة إيضاح (legend) جاهزة للواجهة — لا قيم وهمية."""
    bands = _INDICATOR_BANDS.get(indicator)
    if not bands:
        return []
    return [
        {"band": name, "color": color, "range": [lo, hi],
         "description_ar": desc}
        for lo, hi, name, color, desc in bands
    ]
