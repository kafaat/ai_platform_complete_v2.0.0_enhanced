"""اختبارات محلّلات استيراد حدّ الحقل (geo_import) — أجزاء صرفة offline.

تغطّي: تحليل GeoJSON (Polygon/Feature/FeatureCollection) + KML (مع/بلا
namespace) + نقاط GPS إلى GeoJSON Polygon مُغلَق، ورفض المدخلات التالفة
بـValueError واضح. لا حاجة لقاعدة بيانات أو شبكة.
"""

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
