"""اختبارات محلّلات استيراد حدّ الحقل (geo_import) — أجزاء صرفة offline.

تغطّي: تحليل GeoJSON (Polygon/Feature/FeatureCollection) + KML (مع/بلا
namespace) + نقاط GPS إلى GeoJSON Polygon مُغلَق، ورفض المدخلات التالفة
بـValueError واضح. لا حاجة لقاعدة بيانات أو شبكة.
"""

import math

import pytest
from api.geo_import import parse_geojson, parse_kml, points_to_polygon

# ── عيّنات صغيرة ────────────────────────────────────────────────
_RING = [[45.5, 15.0], [45.6, 15.0], [45.6, 15.1], [45.5, 15.1], [45.5, 15.0]]

GEOJSON_POLYGON = (
    '{"type":"Polygon","coordinates":'
    "[[[45.5,15.0],[45.6,15.0],[45.6,15.1],[45.5,15.1],[45.5,15.0]]]}"
)

GEOJSON_FEATURE = (
    '{"type":"Feature","properties":{"name":"حقل"},'
    '"geometry":{"type":"Polygon","coordinates":'
    "[[[45.5,15.0],[45.6,15.0],[45.6,15.1],[45.5,15.0]]]}}"
)

GEOJSON_FC = (
    '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},'
    '"geometry":{"type":"Point","coordinates":[45.5,15.0]}},'
    '{"type":"Feature","properties":{},"geometry":{"type":"Polygon",'
    '"coordinates":[[[45.5,15.0],[45.6,15.0],[45.6,15.1],[45.5,15.0]]]}}]}'
)

KML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Placemark>
    <name>حقل وادي سبأ</name>
    <Polygon>
      <outerBoundaryIs>
        <LinearRing>
          <coordinates>
            45.5,15.0,0 45.6,15.0,0 45.6,15.1,0 45.5,15.1,0 45.5,15.0,0
          </coordinates>
        </LinearRing>
      </outerBoundaryIs>
    </Polygon>
  </Placemark>
</kml>
"""

KML_NO_NS = """<kml><Placemark><Polygon><outerBoundaryIs><LinearRing>
<coordinates>45.5,15.0 45.6,15.0 45.6,15.1 45.5,15.0</coordinates>
</LinearRing></outerBoundaryIs></Polygon></Placemark></kml>"""


# ── GeoJSON ─────────────────────────────────────────────────────
def test_parse_geojson_polygon():
    geom = parse_geojson(GEOJSON_POLYGON)
    assert geom["type"] == "Polygon"
    assert geom["coordinates"][0] == _RING
    # الحلقة مُغلقة (أوّل = آخر)
    assert geom["coordinates"][0][0] == geom["coordinates"][0][-1]


def test_parse_geojson_feature_closes_ring():
    geom = parse_geojson(GEOJSON_FEATURE)
    ring = geom["coordinates"][0]
    assert geom["type"] == "Polygon"
    # العيّنة غير مُغلقة (3 رؤوس مميّزة) ⇒ يُضاف الإغلاق
    assert ring[0] == ring[-1]
    assert len(ring) == 4


def test_parse_geojson_feature_collection_picks_polygon():
    geom = parse_geojson(GEOJSON_FC)
    assert geom["type"] == "Polygon"
    assert geom["coordinates"][0][0] == [45.5, 15.0]


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "{not json",
        '{"type":"Point","coordinates":[45.5,15.0]}',
        '{"type":"FeatureCollection","features":[]}',
        '{"type":"Polygon","coordinates":[[[45.5,15.0]]]}',  # نقطة واحدة فقط
        "[1,2,3]",  # ليس كائناً
    ],
)
def test_parse_geojson_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_geojson(bad)


# ── KML ─────────────────────────────────────────────────────────
def test_parse_kml_with_namespace():
    geom = parse_kml(KML_SAMPLE)
    assert geom["type"] == "Polygon"
    assert geom["coordinates"][0] == _RING


def test_parse_kml_without_namespace_closes_ring():
    geom = parse_kml(KML_NO_NS)
    ring = geom["coordinates"][0]
    assert geom["type"] == "Polygon"
    assert ring[0] == ring[-1]
    assert len(ring) == 4


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "<kml><Placemark></Placemark></kml>",  # لا Polygon
        "<kml><Polygon><outerBoundaryIs><LinearRing></LinearRing>"
        "</outerBoundaryIs></Polygon></kml>",  # لا coordinates
        "<kml><Polygon><outerBoundaryIs><LinearRing>"
        "<coordinates>45.5 15.0</coordinates></LinearRing>"
        "</outerBoundaryIs></Polygon></kml>",  # توكن بلا فاصلة
        "<kml><unclosed>",  # XML تالف
    ],
)
def test_parse_kml_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_kml(bad)


# ── GPS points ──────────────────────────────────────────────────
def test_points_to_polygon_closes_ring():
    pts = [[45.5, 15.0], [45.6, 15.0], [45.6, 15.1]]
    geom = points_to_polygon(pts)
    ring = geom["coordinates"][0]
    assert geom["type"] == "Polygon"
    assert ring[0] == ring[-1]
    assert len(ring) == 4


def test_points_to_polygon_keeps_closed_ring():
    geom = points_to_polygon(_RING)
    # الحلقة مُغلقة أصلاً ⇒ لا تُضاف نقطة
    assert len(geom["coordinates"][0]) == len(_RING)


@pytest.mark.parametrize(
    "bad",
    [
        [],
        [[45.5, 15.0], [45.6, 15.0]],  # نقطتان فقط
        [[45.5, 15.0], [45.6], [45.6, 15.1]],  # نقطة ناقصة
        [[45.5, "x"], [45.6, 15.0], [45.6, 15.1]],  # غير رقميّة
        "not a list",
    ],
)
def test_points_to_polygon_rejects_malformed(bad):
    with pytest.raises(ValueError):
        points_to_polygon(bad)


# ── تقوية: رفض NaN/Infinity (إحداثيّات غير محدودة) ───────────────
# قيم غير محدودة تُنتج GeoJSON غير قياسيّ وتُفسد حساب المساحة/التقاطع لاحقاً؛
# تُرفض عند الاستخراج لا تُمرَّر بصمت.
@pytest.mark.parametrize(
    "bad",
    [
        '{"type":"Polygon","coordinates":[[[NaN,15.0],[45.6,15.0],[45.6,15.1]]]}',
        '{"type":"Polygon","coordinates":[[[Infinity,15.0],[45.6,15.0],[45.6,15.1]]]}',
        '{"type":"Polygon","coordinates":[[[-Infinity,15.0],[45.6,15.0],[45.6,15.1]]]}',
        '{"type":"Polygon","coordinates":[[[45.5,NaN],[45.6,15.0],[45.6,15.1]]]}',
    ],
)
def test_parse_geojson_rejects_nan_infinity(bad):
    with pytest.raises(ValueError):
        parse_geojson(bad)


@pytest.mark.parametrize(
    "bad_lon",
    [float("nan"), float("inf"), float("-inf")],
)
def test_points_to_polygon_rejects_non_finite(bad_lon):
    with pytest.raises(ValueError):
        points_to_polygon([[bad_lon, 15.0], [45.6, 15.0], [45.6, 15.1]])


@pytest.mark.parametrize(
    "coord_text",
    [
        "nan,15.0 45.6,15.0 45.6,15.1",
        "inf,15.0 45.6,15.0 45.6,15.1",
        "45.5,nan 45.6,15.0 45.6,15.1",
    ],
)
def test_parse_kml_rejects_non_finite(coord_text):
    kml = (
        "<kml><Polygon><outerBoundaryIs><LinearRing>"
        f"<coordinates>{coord_text}</coordinates>"
        "</LinearRing></outerBoundaryIs></Polygon></kml>"
    )
    with pytest.raises(ValueError):
        parse_kml(kml)


def test_parse_geojson_output_is_all_finite():
    """العيّنة الصالحة تُنتج إحداثيّات محدودة فقط (لا NaN/Infinity تتسرّب)."""
    geom = parse_geojson(GEOJSON_POLYGON)
    for lon, lat in geom["coordinates"][0]:
        assert math.isfinite(lon) and math.isfinite(lat)


# ── تقوية: أمان تحليل XML (defusedxml ضدّ XXE / billion-laughs) ───
# محتوى KML قد يأتي من رفع مستخدم غير موثوق عبر import_field؛ يجب رفض
# DTD/الكيانات والكيانات الخارجيّة بـValueError واضح لا توسيعها/قراءتها.
def test_parse_kml_rejects_entity_expansion():
    """billion-laughs: كيان داخليّ يجب أن يُرفض لا أن يُوسَّع."""
    payload = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE d [ <!ENTITY n "99"> ]>\n'
        "<kml><Polygon><outerBoundaryIs><LinearRing>"
        "<coordinates>&n;,1 2,2 3,3</coordinates>"
        "</LinearRing></outerBoundaryIs></Polygon></kml>"
    )
    with pytest.raises(ValueError):
        parse_kml(payload)


def test_parse_kml_rejects_external_entity():
    """XXE: كيان خارجيّ (قراءة ملفّ) يجب أن يُرفض لا أن يُحلّ."""
    payload = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE d [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>\n'
        "<kml><Polygon><outerBoundaryIs><LinearRing>"
        "<coordinates>&xxe;,1 2,2 3,3</coordinates>"
        "</LinearRing></outerBoundaryIs></Polygon></kml>"
    )
    with pytest.raises(ValueError):
        parse_kml(payload)


def test_parse_kml_billion_laughs_rejected_fast():
    """billion-laughs المتداخل: يُرفض دون توسّع (لا تجميد/استنزاف ذاكرة)."""
    payload = (
        '<?xml version="1.0"?>\n'
        "<!DOCTYPE lolz [\n"
        ' <!ENTITY lol "lol">\n'
        ' <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">\n'
        ' <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">\n'
        "]>\n"
        "<kml><Polygon><outerBoundaryIs><LinearRing>"
        "<coordinates>&lol3;,1 2,2 3,3</coordinates>"
        "</LinearRing></outerBoundaryIs></Polygon></kml>"
    )
    with pytest.raises(ValueError):
        parse_kml(payload)
