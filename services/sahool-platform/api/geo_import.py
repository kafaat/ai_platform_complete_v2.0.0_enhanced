"""geo_import.py — محلّلات حدود الحقل من ملفّ/نقاط GPS → GeoJSON Polygon.

دوالّ نقيّة offline (بلا I/O، بلا تبعيّات جديدة — xml.etree من المكتبة القياسيّة
فقط) لاستيراد حدّ حقل بدل رسمه يدويّاً:

* parse_geojson — يستخرج أوّل حلقة Polygon من نصّ GeoJSON (Polygon/Feature/
  FeatureCollection/MultiPolygon) ويُعيد {"type":"Polygon","coordinates":[ring]}.
* parse_kml — يستخرج <Polygon><outerBoundaryIs><LinearRing><coordinates>
  ("lon,lat[,alt] ..." مفصولة بمسافات/أسطر) إلى GeoJSON Polygon.
* points_to_polygon — يحوّل مسار GPS [[lon,lat],...] إلى حلقة مُغلقة.

كلّها ترفع ValueError برسالة واضحة عند مدخل تالف. الناتج يدخل نفس مسار التحقّق
(validate_field_geometry) كالرسم اليدويّ — لا تساهل في صحّة الهندسة هنا، فقط
الاستخراج والإغلاق.
"""

from __future__ import annotations

import json
import math
from xml.etree.ElementTree import Element as _Element
from xml.etree.ElementTree import ParseError as _XMLParseError

# defusedxml: محتوى KML يأتي من رفع المستخدم عبر import_field (مدخل غير موثوق)،
# لذا نمنع توسّع الكيانات/DTD (billion-laughs) وكيانات XXE الخارجيّة بدل
# xml.etree المكشوف. الواجهة (fromstring/ParseError) متطابقة مع المكتبة القياسيّة.
import defusedxml.ElementTree as ET
from defusedxml.common import DefusedXmlException

# الحدّ الأدنى لرؤوس حلقة صالحة (مثلّث) — التحقّق الكامل لاحقاً في
# validate_field_geometry؛ هنا نرفض ما لا يمكن أن يكون مضلّعاً إطلاقاً.
_MIN_RING_POINTS = 3


def _finite(value: float, *, ctx: str) -> float:
    """يرفض NaN/Infinity — قيم غير محدودة تُنتج GeoJSON غير صالح (NaN/Infinity
    ليسا JSON قياسيّاً) وتُفسد حساب المساحة/التقاطع لاحقاً قبل تحقّق النطاق."""
    if not math.isfinite(value):
        raise ValueError(f"إحداثيّة غير محدودة (NaN/Infinity) {ctx}.")
    return value


def _coerce_point(pt: object) -> list[float]:
    """[lon, lat] → [float, float]. يرفض ما ليس زوجاً رقميّاً محدوداً."""
    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
        raise ValueError("نقطة إحداثيّة غير صالحة — يجب أن تكون [lon, lat].")
    try:
        lon = float(pt[0])
        lat = float(pt[1])
    except (TypeError, ValueError) as e:
        raise ValueError("إحداثيّات غير رقميّة في الحلقة.") from e
    return [_finite(lon, ctx="في الحلقة"), _finite(lat, ctx="في الحلقة")]


def _close_ring(ring: list[list[float]]) -> list[list[float]]:
    """يُغلق الحلقة (أوّل نقطة = آخر نقطة) إن لم تكن مُغلقة."""
    if len(ring) < _MIN_RING_POINTS:
        raise ValueError(f"حلقة المضلّع تحتاج {_MIN_RING_POINTS} نقاط على الأقلّ — وُجدت {len(ring)}.")
    if ring[0] != ring[-1]:
        ring = [*ring, list(ring[0])]
    return ring


def _polygon(ring: list[list[float]]) -> dict:
    """يبني GeoJSON Polygon من حلقة خارجيّة (يُغلقها أولاً)."""
    return {"type": "Polygon", "coordinates": [_close_ring(ring)]}


def _extract_first_polygon_ring(geom: dict) -> list[list[float]]:
    """يستخرج أوّل حلقة خارجيّة من geometry (Polygon أو MultiPolygon)."""
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Polygon":
        if not isinstance(coords, list) or not coords:
            raise ValueError("Polygon بلا coordinates صالحة.")
        outer = coords[0]
    elif gtype == "MultiPolygon":
        if not isinstance(coords, list) or not coords or not coords[0]:
            raise ValueError("MultiPolygon بلا coordinates صالحة.")
        outer = coords[0][0]
    else:
        raise ValueError(f"نوع هندسة غير مدعوم للاستيراد: {gtype!r} (المتوقَّع Polygon).")
    if not isinstance(outer, list):
        raise ValueError("حلقة المضلّع الخارجيّة غير صالحة.")
    return [_coerce_point(p) for p in outer]


def _reject_constant(token: str) -> float:
    """يُمرَّر إلى json.loads لرفض ثوابت NaN/Infinity غير القياسيّة بوضوح."""
    raise ValueError(f"قيمة غير صالحة في GeoJSON: {token} (NaN/Infinity غير مسموح).")


def parse_geojson(text: str) -> dict:
    """نصّ GeoJSON → GeoJSON Polygon (أوّل حلقة Polygon).

    يقبل: Polygon/MultiPolygon مباشرة، أو Feature يلفّ أحدهما، أو
    FeatureCollection (يأخذ أوّل Feature ذي Polygon/MultiPolygon).
    يرفع ValueError عند JSON تالف أو غياب أيّ مضلّع.
    """
    if not text or not text.strip():
        raise ValueError("محتوى GeoJSON فارغ.")
    try:
        # parse_constant يرفض NaN/Infinity/-Infinity (ليست JSON قياسيّاً ولا
        # إحداثيّات صالحة) قبل أن تتسرّب إلى الهندسة.
        data = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, TypeError) as e:
        raise ValueError(f"GeoJSON غير صالح (JSON تالف): {e}") from e
    if not isinstance(data, dict):
        raise ValueError("GeoJSON غير صالح — المتوقَّع كائن JSON.")

    dtype = data.get("type")
    if dtype in ("Polygon", "MultiPolygon"):
        return _polygon(_extract_first_polygon_ring(data))
    if dtype == "Feature":
        geom = data.get("geometry")
        if not isinstance(geom, dict):
            raise ValueError("Feature بلا geometry صالحة.")
        return _polygon(_extract_first_polygon_ring(geom))
    if dtype == "FeatureCollection":
        features = data.get("features")
        if not isinstance(features, list) or not features:
            raise ValueError("FeatureCollection بلا features.")
        for feat in features:
            geom = feat.get("geometry") if isinstance(feat, dict) else None
            if isinstance(geom, dict) and geom.get("type") in ("Polygon", "MultiPolygon"):
                return _polygon(_extract_first_polygon_ring(geom))
        raise ValueError("لا يوجد Polygon في FeatureCollection.")
    raise ValueError(f"نوع GeoJSON غير مدعوم: {dtype!r}.")


def _strip_ns(tag: str) -> str:
    """يزيل namespace من وسم XML ({ns}LocalName → LocalName)."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_first_local(root: _Element, name: str) -> _Element | None:
    """أوّل عنصر باسم محليّ مطابق (يتجاهل namespace الـKML)."""
    for el in root.iter():
        if _strip_ns(el.tag) == name:
            return el
    return None


def _parse_kml_coords(text: str) -> list[list[float]]:
    """نصّ <coordinates> الـKML ("lon,lat[,alt]" مفصولة) → [[lon,lat],...]."""
    pts: list[list[float]] = []
    for token in text.replace("\n", " ").replace("\t", " ").split():
        token = token.strip()
        if not token:
            continue
        parts = token.split(",")
        if len(parts) < 2:
            raise ValueError(f"إحداثيّة KML غير صالحة: {token!r} (المتوقَّع lon,lat).")
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except ValueError as e:
            raise ValueError(f"إحداثيّة KML غير رقميّة: {token!r}.") from e
        pts.append([_finite(lon, ctx=f"في {token!r}"), _finite(lat, ctx=f"في {token!r}")])
    return pts


def parse_kml(text: str) -> dict:
    """نصّ KML → GeoJSON Polygon (أوّل <Polygon> خارجيّ).

    يستخرج Polygon/outerBoundaryIs/LinearRing/coordinates. xml.etree فقط
    (بلا تبعيّات). يرفع ValueError عند XML تالف أو غياب Polygon/coordinates.
    """
    if not text or not text.strip():
        raise ValueError("محتوى KML فارغ.")
    try:
        # defusedxml.fromstring يرفض DTD/الكيانات (billion-laughs) والكيانات
        # الخارجيّة (XXE) — محتوى KML قد يكون رفعاً غير موثوق من المستخدم.
        root = ET.fromstring(text)
    except DefusedXmlException as e:
        raise ValueError(f"KML غير آمن (DTD/كيانات XML غير مسموح بها): {e}") from e
    except _XMLParseError as e:
        raise ValueError(f"KML غير صالح (XML تالف): {e}") from e

    polygon = _find_first_local(root, "Polygon")
    if polygon is None:
        raise ValueError("لا يوجد <Polygon> في ملفّ KML.")
    outer = _find_first_local(polygon, "outerBoundaryIs")
    ring_src = outer if outer is not None else polygon
    coords_el = _find_first_local(ring_src, "coordinates")
    if coords_el is None or not (coords_el.text and coords_el.text.strip()):
        raise ValueError("لا يوجد <coordinates> داخل Polygon في KML.")

    ring = _parse_kml_coords(coords_el.text)
    return _polygon(ring)


def points_to_polygon(points: list[list[float]]) -> dict:
    """مسار GPS [[lon,lat],...] → GeoJSON Polygon (يُغلق الحلقة).

    لمشي حدود الحقل بنقاط GPS. يرفع ValueError عند نقاط ناقصة/غير رقميّة أو
    أقلّ من الحدّ الأدنى لمضلّع.
    """
    if not isinstance(points, list):
        raise ValueError("نقاط GPS يجب أن تكون قائمة [[lon,lat],...].")
    ring = [_coerce_point(p) for p in points]
    return _polygon(ring)
