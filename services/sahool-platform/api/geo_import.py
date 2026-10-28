"""geo_import.py — محلّلات حدود الحقل من ملفّ/نقاط GPS → GeoJSON Polygon.

دوالّ نقيّة offline (بلا I/O، بلا تبعيّات جديدة — xml.etree من المكتبة القياسيّة
فقط) لاستيراد حدّ حقل بدل رسمه يدويّاً:

* parse_geojson — يستخرج المضلّع الوحيد من نصّ GeoJSON (Polygon/Feature/
  FeatureCollection/MultiPolygon بجزء واحد) بكلّ حلقاته: الخارجيّة **والثقوب**،
  ويحمل عضو ``crs`` المُضمَّن (إن وُجد) إلى الحارس ليرفض غير WGS84.
* parse_kml — يستخرج <Polygon> الوحيد: outerBoundaryIs + كلّ innerBoundaryIs
  ("lon,lat[,alt] ..." مفصولة بمسافات/أسطر) إلى GeoJSON Polygon.
* points_to_polygon — يحوّل مسار GPS [[lon,lat],...] إلى حلقة مُغلقة.

لا اختيار صامت: ملفّ بعدّة مضلّعات (MultiPolygon بأجزاء، عدّة Features، عدّة
<Polygon>) يُرفض برسالة تذكر العدد بدل أخذ الأوّل وإسقاط الباقي — حفظ الحقل
(validate_boundary_for_save) يقبل Polygon واحداً فقط.

كلّها ترفع ValueError برسالة واضحة عند مدخل تالف. الناتج يدخل نفس مسار التحقّق
(guard_field_geometry) كالرسم اليدويّ — لا تساهل في صحّة الهندسة هنا، فقط
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


def _polygon(ring: list[list[float]], holes: list[list[list[float]]] | None = None) -> dict:
    """يبني GeoJSON Polygon من حلقة خارجيّة + ثقوب (يُغلق كلّ حلقة أولاً)."""
    return {
        "type": "Polygon",
        "coordinates": [_close_ring(ring), *[_close_ring(h) for h in holes or []]],
    }


def _multiple_polygons_error(count: int, where: str) -> ValueError:
    return ValueError(
        f"{where} يحوي {count} مضلّعات منفصلة — حفظ الحقل يقبل مضلّعاً واحداً. "
        "صدِّر كلّ حقل في ملفّ مستقلّ (أو ادمجها في مضلّع واحد) ثمّ أعد الاستيراد."
    )


def _extract_polygon_rings(geom: dict) -> list[list[list[float]]]:
    """يستخرج حلقات المضلّع الوحيد (الخارجيّة ثمّ الثقوب) من Polygon أو MultiPolygon.

    MultiPolygon بأكثر من جزء يُرفض صراحةً (لا يُؤخذ الجزء الأوّل بصمت).
    """
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Polygon":
        if not isinstance(coords, list) or not coords:
            raise ValueError("Polygon بلا coordinates صالحة.")
        rings = coords
    elif gtype == "MultiPolygon":
        if not isinstance(coords, list) or not coords or not coords[0]:
            raise ValueError("MultiPolygon بلا coordinates صالحة.")
        if len(coords) > 1:
            raise _multiple_polygons_error(len(coords), "MultiPolygon")
        rings = coords[0]
    else:
        raise ValueError(f"نوع هندسة غير مدعوم للاستيراد: {gtype!r} (المتوقَّع Polygon).")
    if not isinstance(rings, list) or not all(isinstance(r, list) for r in rings):
        raise ValueError("حلقة المضلّع الخارجيّة غير صالحة.")
    return [[_coerce_point(p) for p in ring] for ring in rings]


def _polygon_from_rings(rings: list[list[list[float]]], crs: object = None) -> dict:
    out = _polygon(rings[0], rings[1:])
    if crs is not None:
        # يُحمَل كما هو ليقرّر guard_field_geometry (مصدر واحد لسياسة CRS) — لا يُسقَط.
        out["crs"] = crs
    return out


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
    # crs الأخصّ يغلب (geometry ← Feature ← الجذر) كما في GeoJSON 2008.
    root_crs = data.get("crs")
    if dtype in ("Polygon", "MultiPolygon"):
        return _polygon_from_rings(_extract_polygon_rings(data), root_crs)
    if dtype == "Feature":
        geom = data.get("geometry")
        if not isinstance(geom, dict):
            raise ValueError("Feature بلا geometry صالحة.")
        crs = geom.get("crs", root_crs)
        return _polygon_from_rings(_extract_polygon_rings(geom), crs)
    if dtype == "FeatureCollection":
        features = data.get("features")
        if not isinstance(features, list) or not features:
            raise ValueError("FeatureCollection بلا features.")
        polygonal = [
            feat
            for feat in features
            if isinstance(feat, dict)
            and isinstance(feat.get("geometry"), dict)
            and feat["geometry"].get("type") in ("Polygon", "MultiPolygon")
        ]
        if not polygonal:
            raise ValueError("لا يوجد Polygon في FeatureCollection.")
        if len(polygonal) > 1:
            raise _multiple_polygons_error(len(polygonal), "FeatureCollection")
        feat = polygonal[0]
        geom = feat["geometry"]
        crs = geom.get("crs", feat.get("crs", root_crs))
        return _polygon_from_rings(_extract_polygon_rings(geom), crs)
    raise ValueError(f"نوع GeoJSON غير مدعوم: {dtype!r}.")


def _strip_ns(tag: str) -> str:
    """يزيل namespace من وسم XML ({ns}LocalName → LocalName)."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_all_local(root: _Element, name: str) -> list[_Element]:
    """كلّ العناصر باسم محليّ مطابق (يتجاهل namespace الـKML)."""
    return [el for el in root.iter() if _strip_ns(el.tag) == name]


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
    """نصّ KML → GeoJSON Polygon (الـ<Polygon> الوحيد بحدّه الخارجيّ وثقوبه).

    يستخرج Polygon/outerBoundaryIs + كلّ innerBoundaryIs/LinearRing/coordinates.
    KML بإحداثيّات WGS84 lon,lat بالمواصفة فلا CRS يُقرأ. يرفع ValueError عند XML
    تالف أو غياب Polygon/coordinates أو تعدّد <Polygon> (لا يُؤخذ الأوّل بصمت).
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

    polygons = _find_all_local(root, "Polygon")
    if not polygons:
        raise ValueError("لا يوجد <Polygon> في ملفّ KML.")
    if len(polygons) > 1:
        raise _multiple_polygons_error(len(polygons), "ملفّ KML")
    polygon = polygons[0]
    outers = _find_all_local(polygon, "outerBoundaryIs")
    if len(outers) > 1:
        raise ValueError(f"Polygon في KML يحوي {len(outers)} <outerBoundaryIs>؛ المتوقَّع واحد.")
    ring_src = outers[0] if outers else polygon
    outer_coords = _find_all_local(ring_src, "coordinates")
    if outers and len(outer_coords) > 1:
        # حلقةٌ خارجيّة واحدة لكلّ Polygon؛ أخذ الأولى يُسقط الباقي بصمت.
        raise ValueError(
            f"<outerBoundaryIs> في KML يحوي {len(outer_coords)} حلقات؛ المتوقَّع حلقة واحدة."
        )
    coords_el = outer_coords[0] if outer_coords else None
    if coords_el is None or not (coords_el.text and coords_el.text.strip()):
        raise ValueError("لا يوجد <coordinates> داخل Polygon في KML.")

    ring = _parse_kml_coords(coords_el.text)
    holes: list[list[list[float]]] = []
    for inner in _find_all_local(polygon, "innerBoundaryIs"):
        # بعض الكتّاب يضعون عدّة <LinearRing> في <innerBoundaryIs> واحد (خارج مخطّط
        # KML 2.2)؛ كلّها ثقوب، فأخذ الأولى وحدها يُضخّم المساحة بصمت.
        hole_els = _find_all_local(inner, "coordinates")
        if not hole_els:
            raise ValueError("<innerBoundaryIs> بلا <coordinates> في KML.")
        for hole_el in hole_els:
            if not (hole_el.text and hole_el.text.strip()):
                raise ValueError("<innerBoundaryIs> بـ<coordinates> فارغ في KML.")
            holes.append(_parse_kml_coords(hole_el.text))
    return _polygon(ring, holes)


def points_to_polygon(points: list[list[float]]) -> dict:
    """مسار GPS [[lon,lat],...] → GeoJSON Polygon (يُغلق الحلقة).

    لمشي حدود الحقل بنقاط GPS. يرفع ValueError عند نقاط ناقصة/غير رقميّة أو
    أقلّ من الحدّ الأدنى لمضلّع.
    """
    if not isinstance(points, list):
        raise ValueError("نقاط GPS يجب أن تكون قائمة [[lon,lat],...].")
    ring = [_coerce_point(p) for p in points]
    return _polygon(ring)
