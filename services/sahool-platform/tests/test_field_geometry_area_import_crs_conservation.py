"""اختبارات وحدة: مساحة الحقل الصافية، خطّ التاريخ، الاستيراد بلا فقد، CRS المُضمَّن،
وحفظ المساحة في الدمج/الانقسام (تدقيق الاستشعار عن بعد 2026-10-27).

كلّ اختبار هنا شاهدُ انحدار لادّعاءٍ مُتحقَّق منه على الشيفرة غير المُعدَّلة:

* G-AREA-1 — ``guard_field_geometry`` كان يجمع الحلقات الخارجيّة فقط فيتجاهل الثقوب
  (118.85 هـ لمستطيل بثقب ٣٦٪ = مساحته بلا ثقب) فتُخزَّن في ``fields.area_ha``.
* G-AREA-2 — ``polygon_area_m2`` يطرح خطوط الطول خاماً فحلقة تعبر خطّ التاريخ
  تُعطي ~4.3×10¹⁰ م² بدل ~1.2×10⁶ م²، والحارس يرفضها بسبب مُضلِّل (area_too_large).
* G-IMP-1 — ``parse_geojson``/``parse_kml`` تأخذ أوّل حلقة خارجيّة فتُسقط الثقوب
  والأجزاء والمعالم الإضافيّة بصمت.
* G-CRS-1 — ``crs`` المُضمَّن في GeoJSON يُسقَط؛ EPSG:3857 بأرقام داخل نطاق lon/lat
  يُقبَل درجاتٍ.
* G-SPLIT-1 — الدمج/الانقسام لا يتحقّقان أنّ اتّحاد الناتج يساوي المصدر.

المرجع المستقلّ للمساحة: مساحة «مستطيل» lon/lat على الكرة ذات نصف القطر
6371008.8 م مغلقة الصيغة R²·Δλ·(sin φ₂ − sin φ₁) — لا تمرّ بالشيفرة المُختبَرة.
"""

from __future__ import annotations

import json
import math
import uuid

import pytest

pytestmark = pytest.mark.unit

_R = 6371008.8


def _rect(lon0: float, lat0: float, lon1: float, lat1: float) -> list[list[float]]:
    return [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]


def _band_area_m2(lon0: float, lat0: float, lon1: float, lat1: float) -> float:
    """مساحة مستطيل lon/lat على الكرة — صيغة مغلقة مستقلّة عن الشيفرة."""
    dlon = math.radians(lon1 - lon0)
    return abs(_R * _R * dlon * (math.sin(math.radians(lat1)) - math.sin(math.radians(lat0))))


_OUTER = _rect(44.0, 16.0, 44.01, 16.01)
_HOLE = _rect(44.002, 16.002, 44.008, 16.008)
_OTHER = _rect(44.02, 16.0, 44.03, 16.01)


# ─── G-AREA-1: المساحة الصافية = الخارجيّة − الثقوب ─────────────────────────


def test_guard_area_subtracts_holes():
    from api.gis_geometry_guard import guard_field_geometry

    expected_m2 = _band_area_m2(44.0, 16.0, 44.01, 16.01) - _band_area_m2(
        44.002, 16.002, 44.008, 16.008
    )
    holed = guard_field_geometry({"type": "Polygon", "coordinates": [_OUTER, _HOLE]})
    # الثقب محفوظ في الهندسة…
    assert len(holed.geometry["coordinates"]) == 2
    # …ومطروح من المساحة (تقريب الحارس ٤ منازل عشريّة للهكتار = ١ م²).
    assert holed.area_ha * 10_000 == pytest.approx(expected_m2, abs=1.0)
    plain = guard_field_geometry({"type": "Polygon", "coordinates": [_OUTER]})
    assert holed.area_ha < plain.area_ha * 0.7


def test_guard_area_subtracts_holes_per_multipolygon_part():
    from api.gis_geometry_guard import guard_field_geometry

    expected_m2 = (
        _band_area_m2(44.0, 16.0, 44.01, 16.01)
        - _band_area_m2(44.002, 16.002, 44.008, 16.008)
        + _band_area_m2(44.02, 16.0, 44.03, 16.01)
    )
    guarded = guard_field_geometry(
        {"type": "MultiPolygon", "coordinates": [[_OUTER, _HOLE], [_OTHER]]}
    )
    assert guarded.area_ha * 10_000 == pytest.approx(expected_m2, abs=1.0)


def test_guard_hole_area_independent_of_ring_winding():
    from api.gis_geometry_guard import guard_field_geometry

    a = guard_field_geometry({"type": "Polygon", "coordinates": [_OUTER, _HOLE]}, repair=False)
    b = guard_field_geometry(
        {"type": "Polygon", "coordinates": [_OUTER[::-1], _HOLE[::-1]]}, repair=False
    )
    assert a.area_ha == pytest.approx(b.area_ha, abs=1e-4)


def test_validate_geometry_preview_area_subtracts_holes():
    """معاينة POST /fields/validate-geometry تُعلن المساحة نفسها التي ستُخزَّن."""
    from api.geospatial_integrity import validate_field_geometry
    from api.gis_geometry_guard import guard_field_geometry

    geom = {"type": "Polygon", "coordinates": [_OUTER, _HOLE]}
    preview = validate_field_geometry(geom)
    assert preview.valid
    assert preview.computed_area_ha == pytest.approx(guard_field_geometry(geom).area_ha, abs=1e-4)


def test_guard_spherical_area_within_documented_tolerance_of_wgs84():
    """النموذج كرويّ موثَّق (R=6371008.8)؛ انحرافه عن إهليلج WGS84 عند عرض اليمن < 0.5٪."""
    pyproj = pytest.importorskip("pyproj")
    from api.gis_geometry_guard import guard_field_geometry

    geod = pyproj.Geod(ellps="WGS84")

    def ell(ring):
        lons, lats = zip(*ring, strict=True)
        return abs(geod.polygon_area_perimeter(lons, lats)[0])

    ref = ell(_OUTER) - ell(_HOLE)
    got = guard_field_geometry({"type": "Polygon", "coordinates": [_OUTER, _HOLE]}).area_ha
    assert abs(got * 10_000 - ref) / ref < 0.005


# مساحة WGS84 الجيوديسيّة المرجعيّة للحالة نفسها (م²)، مُقاسةً مرّةً بـ
# pyproj 3.7.2 ``Geod(ellps="WGS84").polygon_area_perimeter``: الخارجيّة 1184399.56 −
# الثقب 426383.84. مُثبَّتةٌ رقماً لأنّ pyproj ليس تبعيّةً للمنصّة ولا لـCI، فالاختبار
# أعلاه يُتخطّى هناك دائماً ويبقى السماح الموثَّق (< 0.5٪) بلا حارس حاجب.
_WGS84_NET_AREA_M2 = 758015.72


def test_guard_spherical_area_tolerance_pinned_without_pyproj():
    """السماح الموثَّق مُثبَّت في CI بلا pyproj (مرجعٌ مُقاسٌ لا يمرّ بالشيفرة المُختبَرة)."""
    from api.gis_geometry_guard import guard_field_geometry

    got = guard_field_geometry({"type": "Polygon", "coordinates": [_OUTER, _HOLE]}).area_ha
    assert abs(got * 10_000 - _WGS84_NET_AREA_M2) / _WGS84_NET_AREA_M2 < 0.005


# ─── G-AREA-2: خطّ التاريخ ────────────────────────────────────────────────


def test_polygon_area_wraps_longitude_difference_across_antimeridian():
    from api.geospatial_integrity import polygon_area_m2

    crossing = [(179.995, -16.0), (-179.995, -16.0), (-179.995, -15.99), (179.995, -15.99)]
    expected = _band_area_m2(179.995, -16.0, 180.005, -15.99)
    assert polygon_area_m2(crossing) == pytest.approx(expected, rel=1e-6)


def test_guard_rejects_antimeridian_crossing_with_named_cause():
    """التخزين القانونيّ (bbox/مركز من منتصف bbox/تقاطع مستوٍ) لا يدعم الالتفاف —
    يُرفض بسببٍ مُسمّى لا بـ«مساحة كبيرة» مُضلِّلة."""
    from api.gis_geometry_guard import guard_field_geometry

    ring = [[179.995, -16.0], [-179.995, -16.0], [-179.995, -15.99], [179.995, -15.99]]
    with pytest.raises(ValueError) as caught:
        guard_field_geometry({"type": "Polygon", "coordinates": [ring]})
    issues = str(caught.value).split(",")
    assert "antimeridian_crossing" in issues
    assert "area_too_large" not in issues


# ─── G-IMP-1: الاستيراد لا يفقد ثقوباً ولا أجزاء ولا معالم بصمت ─────────────────


def test_import_geojson_preserves_holes():
    from api.geo_import import parse_geojson

    geom = parse_geojson(json.dumps({"type": "Polygon", "coordinates": [_OUTER, _HOLE]}))
    assert geom["type"] == "Polygon"
    assert geom["coordinates"] == [_OUTER, _HOLE]


def test_import_geojson_single_part_multipolygon_keeps_holes():
    from api.geo_import import parse_geojson

    geom = parse_geojson(json.dumps({"type": "MultiPolygon", "coordinates": [[_OUTER, _HOLE]]}))
    assert geom == {"type": "Polygon", "coordinates": [_OUTER, _HOLE]}


def test_import_geojson_rejects_multipart_instead_of_taking_first():
    from api.geo_import import parse_geojson

    with pytest.raises(ValueError, match="2"):
        parse_geojson(json.dumps({"type": "MultiPolygon", "coordinates": [[_OUTER], [_OTHER]]}))


def test_import_geojson_rejects_multiple_polygon_features_instead_of_taking_first():
    from api.geo_import import parse_geojson

    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Polygon", "coordinates": [_OUTER]},
            },
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Polygon", "coordinates": [_OTHER]},
            },
        ],
    }
    with pytest.raises(ValueError, match="2"):
        parse_geojson(json.dumps(fc))


def test_import_kml_preserves_inner_boundary():
    from api.geo_import import parse_kml

    def coords(ring):
        return " ".join(f"{x},{y},0" for x, y in ring)

    kml = (
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Polygon>'
        f"<outerBoundaryIs><LinearRing><coordinates>{coords(_OUTER)}</coordinates>"
        "</LinearRing></outerBoundaryIs>"
        f"<innerBoundaryIs><LinearRing><coordinates>{coords(_HOLE)}</coordinates>"
        "</LinearRing></innerBoundaryIs>"
        "</Polygon></Placemark></kml>"
    )
    assert parse_kml(kml) == {"type": "Polygon", "coordinates": [_OUTER, _HOLE]}


def test_import_kml_rejects_multiple_polygons_instead_of_taking_first():
    from api.geo_import import parse_kml

    def poly(ring):
        pts = " ".join(f"{x},{y}" for x, y in ring)
        return (
            "<Polygon><outerBoundaryIs><LinearRing>"
            f"<coordinates>{pts}</coordinates>"
            "</LinearRing></outerBoundaryIs></Polygon>"
        )

    kml = f"<kml><Placemark><MultiGeometry>{poly(_OUTER)}{poly(_OTHER)}</MultiGeometry></Placemark></kml>"
    with pytest.raises(ValueError, match="2"):
        parse_kml(kml)


def _kml_ring(ring) -> str:
    pts = " ".join(f"{x},{y}" for x, y in ring)
    return f"<LinearRing><coordinates>{pts}</coordinates></LinearRing>"


_HOLE_2 = _rect(44.0085, 16.0085, 44.0095, 16.0095)


def test_import_kml_keeps_every_ring_in_one_inner_boundary():
    """كتّابٌ يضعون عدّة <LinearRing> في <innerBoundaryIs> واحد (خارج مخطّط KML 2.2
    لكنّه شائع)؛ أخذ الأوّل يُسقط الثقوب التالية بصمت فتتضخّم المساحة."""
    from api.geo_import import parse_kml

    kml = (
        "<kml><Placemark><Polygon>"
        f"<outerBoundaryIs>{_kml_ring(_OUTER)}</outerBoundaryIs>"
        f"<innerBoundaryIs>{_kml_ring(_HOLE)}{_kml_ring(_HOLE_2)}</innerBoundaryIs>"
        "</Polygon></Placemark></kml>"
    )
    assert parse_kml(kml) == {"type": "Polygon", "coordinates": [_OUTER, _HOLE, _HOLE_2]}


def test_import_kml_rejects_several_rings_in_outer_boundary():
    """حدٌّ خارجيّ بأكثر من حلقة غامض (أيّها الحقل؟) فيُرفض لا يُؤخذ أوّلها بصمت."""
    from api.geo_import import parse_kml

    kml = (
        "<kml><Placemark><Polygon>"
        f"<outerBoundaryIs>{_kml_ring(_OUTER)}{_kml_ring(_OTHER)}</outerBoundaryIs>"
        "</Polygon></Placemark></kml>"
    )
    with pytest.raises(ValueError, match="outerBoundaryIs"):
        parse_kml(kml)


# ─── G-CRS-1: CRS المُضمَّن يُحترَم أو يُرفض ───────────────────────────────────

_EPSG_3857 = {"type": "name", "properties": {"name": "EPSG:3857"}}
_CRS84 = {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}


@pytest.mark.parametrize(
    "geojson",
    [
        {"type": "Polygon", "coordinates": [_OUTER], "crs": _EPSG_3857},
        {
            "type": "Feature",
            "crs": _EPSG_3857,
            "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [_OUTER]},
        },
        {
            "type": "FeatureCollection",
            "crs": _EPSG_3857,
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Polygon", "coordinates": [_OUTER]},
                }
            ],
        },
    ],
    ids=["geometry", "feature", "collection"],
)
def test_guard_rejects_embedded_projected_crs(geojson):
    from api.gis_geometry_guard import guard_field_geometry

    with pytest.raises(ValueError) as caught:
        guard_field_geometry(geojson)
    assert "invalid_crs" in str(caught.value).split(",")


def test_guard_accepts_embedded_wgs84_crs_forms():
    from api.gis_geometry_guard import guard_field_geometry

    for crs in (_CRS84, {"type": "name", "properties": {"name": "EPSG:4326"}}):
        guarded = guard_field_geometry({"type": "Polygon", "coordinates": [_OUTER], "crs": crs})
        assert "crs" not in guarded.geometry  # الناتج القانونيّ بلا crs (4326 ضمنيّاً)


@pytest.mark.parametrize(
    "name",
    [
        "WGS84 / UTM zone 38N",
        "WGS84 / Pseudo-Mercator",
        "EPSG:43260",
        "urn:ogc:def:crs:EPSG::32638 (WGS84)",
    ],
)
def test_guard_rejects_embedded_crs_name_that_merely_contains_a_wgs84_token(name):
    """crs المُضمَّن يُطابَق بالشكل الكامل لا بالاحتواء: «WGS84 / UTM zone 38N» إسقاطٌ
    لا 4326 ولو احتوى الرمز «WGS84»."""
    from api.gis_geometry_guard import guard_field_geometry

    crs = {"type": "name", "properties": {"name": name}}
    with pytest.raises(ValueError) as caught:
        guard_field_geometry({"type": "Polygon", "coordinates": [_OUTER], "crs": crs})
    assert "invalid_crs" in str(caught.value).split(",")


@pytest.mark.parametrize(
    "name",
    [
        "EPSG:4326",
        "epsg:4326",
        "urn:ogc:def:crs:EPSG::4326",
        "urn:ogc:def:crs:EPSG:6.6:4326",
        "http://www.opengis.net/def/crs/EPSG/0/4326",
        "urn:ogc:def:crs:OGC:1.3:CRS84",
        "urn:ogc:def:crs:OGC::CRS84",
        "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "CRS:84",
        "OGC:CRS84",
        "WGS84",
        "WGS 84",
    ],
)
def test_guard_accepts_canonical_embedded_wgs84_names(name):
    from api.gis_geometry_guard import guard_field_geometry

    crs = {"type": "name", "properties": {"name": name}}
    guarded = guard_field_geometry({"type": "Polygon", "coordinates": [_OUTER], "crs": crs})
    assert "crs" not in guarded.geometry


def test_guard_rejects_embedded_crs_even_when_declared_crs_is_wgs84():
    from api.gis_geometry_guard import guard_field_geometry

    with pytest.raises(ValueError) as caught:
        guard_field_geometry(
            {"type": "Polygon", "coordinates": [_OUTER], "crs": _EPSG_3857},
            declared_crs="EPSG:4326",
        )
    assert "invalid_crs" in str(caught.value).split(",")


@pytest.mark.parametrize("multipart", [False, True], ids=["polygon", "multipolygon"])
def test_validate_geometry_preview_rejects_embedded_projected_crs(multipart):
    """معاينة POST /fields/validate-geometry لا تقبل ما سيرفضه الحفظ."""
    from api.geospatial_integrity import validate_field_geometry

    geom = (
        {"type": "MultiPolygon", "coordinates": [[_OUTER], [_OTHER]], "crs": _EPSG_3857}
        if multipart
        else {"type": "Polygon", "coordinates": [_OUTER], "crs": _EPSG_3857}
    )
    preview = validate_field_geometry(geom)
    assert not preview.valid
    assert "invalid_crs" in [i.code for i in preview.issues]


def test_import_geojson_carries_embedded_crs_to_the_guard():
    from api.geo_import import parse_geojson
    from api.gis_geometry_guard import guard_field_geometry

    text = json.dumps(
        {
            "type": "FeatureCollection",
            "crs": _EPSG_3857,
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Polygon", "coordinates": [_OUTER]},
                }
            ],
        }
    )
    with pytest.raises(ValueError) as caught:
        guard_field_geometry(parse_geojson(text))
    assert "invalid_crs" in str(caught.value).split(",")


def test_invalid_crs_error_detail_names_the_cause():
    from api.gis_geometry_guard import field_geometry_error_detail

    detail = field_geometry_error_detail(ValueError("invalid_crs"))
    assert detail["code"] == "invalid_field_geometry"
    assert "EPSG:4326" in detail["message_ar"]


# ─── G-SPLIT-1: حفظ المساحة في الدمج/الانقسام ───────────────────────────────
# مربّعان متجاوران ≈ ١١ هـ لكلٍّ (داخل حدود الحارس)، واتّحادهما مستطيل واحد.
_SQ_A = {"type": "Polygon", "coordinates": [_rect(44.0, 15.0, 44.003, 15.003)]}
_SQ_B = {"type": "Polygon", "coordinates": [_rect(44.003, 15.0, 44.006, 15.003)]}
_SQ_AB = {"type": "Polygon", "coordinates": [_rect(44.0, 15.0, 44.006, 15.003)]}
_SQ_FAR = {"type": "Polygon", "coordinates": [_rect(44.1, 15.1, 44.103, 15.103)]}


def test_conservation_accepts_exact_split_and_merge():
    from api.gis_geometry_guard import area_conservation_issues

    assert area_conservation_issues([_SQ_AB], [_SQ_A, _SQ_B]) == []
    assert area_conservation_issues([_SQ_A, _SQ_B], [_SQ_AB]) == []


def test_conservation_flags_lost_extra_and_overlapping_area():
    from api.gis_geometry_guard import area_conservation_issues

    # انقسام يفقد نصف المصدر ويضيف قطعة خارجه.
    issues = area_conservation_issues([_SQ_AB], [_SQ_A, _SQ_FAR])
    assert "source_area_not_covered" in issues
    assert "result_outside_source" in issues
    # وليدان متطابقان (تداخل كامل) يغطّيان نصف المصدر مرّتين.
    assert "result_parts_overlap" in area_conservation_issues([_SQ_A], [_SQ_A, _SQ_A])
    # دمج يحذف أحد المصدرين.
    assert area_conservation_issues([_SQ_A, _SQ_B], [_SQ_A]) == ["source_area_not_covered"]


class _User:
    def __init__(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.role = "manager"


class _Conn:
    def __init__(self, geometries: dict[str, object]):
        self._geometries = geometries
        self.executes: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql, *args):  # noqa: ANN001
        if "FROM fields" in sql and args and args[0] in self._geometries:
            geom = self._geometries[args[0]]
            # asyncpg يُعيد JSONB نصّاً بلا codec — نُحاكيه.
            return {
                "field_id": args[0],
                "name": f"src-{args[0]}",
                "crop": "قمح",
                "geometry": json.dumps(geom) if geom is not None else None,
            }
        return None

    async def fetchval(self, sql, *args):  # noqa: ANN001
        return 0

    async def execute(self, sql, *args):  # noqa: ANN001
        self.executes.append((sql, args))
        return "INSERT 0 1"


class _Tx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _BG:
    def __init__(self):
        self.tasks: list = []

    def add_task(self, fn, **kw):  # noqa: ANN001
        self.tasks.append(kw)


@pytest.fixture
def fields_mod(monkeypatch):
    import api.main  # noqa: F401 — يحلّ دورة الاستيراد (يسجّل الموجِّهات)
    import api.routers.fields as m

    async def _emit(*a, **kw):  # noqa: ANN001
        return None

    async def _revision(conn, **kw):  # noqa: ANN001
        return 1

    async def _stale(conn, **kw):  # noqa: ANN001
        return None

    async def _state(conn, field_id):  # noqa: ANN001
        return {"changed": False, "state": {}}

    import api.field_state_projection as fsp

    monkeypatch.setattr(m, "_emit_domain_event", _emit)
    monkeypatch.setattr(m, "save_field_geometry_revision", _revision)
    monkeypatch.setattr(m, "mark_raster_cache_stale", _stale)
    monkeypatch.setattr(fsp, "recompute_field_state", _state)
    return m


def _use_conn(monkeypatch, fields_mod, conn):
    monkeypatch.setattr(fields_mod, "tenant_connection", lambda user: _Tx(conn))


async def test_split_rejects_children_that_do_not_reconstruct_source(fields_mod, monkeypatch):
    from fastapi import HTTPException

    conn = _Conn({"src": _SQ_AB})
    _use_conn(monkeypatch, fields_mod, conn)
    req = fields_mod.FieldSplitRequest(
        source_field_id="src",
        children=[{"name": "أ", "geometry": _SQ_A}, {"name": "ب", "geometry": _SQ_FAR}],
    )
    with pytest.raises(HTTPException) as caught:
        await fields_mod.split_field(req=req, background_tasks=_BG(), user=_User(), idem=None)
    assert caught.value.status_code == 422
    assert caught.value.detail["code"] == "field_area_not_conserved"
    assert "source_area_not_covered" in caught.value.detail["issues"]
    assert conn.executes == []  # لا كتابة قبل التحقّق


async def test_split_rejects_overlapping_children(fields_mod, monkeypatch):
    from fastapi import HTTPException

    conn = _Conn({"src": _SQ_AB})
    _use_conn(monkeypatch, fields_mod, conn)
    req = fields_mod.FieldSplitRequest(
        source_field_id="src",
        children=[{"name": "أ", "geometry": _SQ_AB}, {"name": "ب", "geometry": _SQ_B}],
    )
    with pytest.raises(HTTPException) as caught:
        await fields_mod.split_field(req=req, background_tasks=_BG(), user=_User(), idem=None)
    assert caught.value.status_code == 422
    assert "result_parts_overlap" in caught.value.detail["issues"]
    assert conn.executes == []


async def test_split_accepts_conserving_children(fields_mod, monkeypatch):
    conn = _Conn({"src": _SQ_AB})
    _use_conn(monkeypatch, fields_mod, conn)
    req = fields_mod.FieldSplitRequest(
        source_field_id="src",
        children=[{"name": "أ", "geometry": _SQ_A}, {"name": "ب", "geometry": _SQ_B}],
    )
    out = await fields_mod.split_field(req=req, background_tasks=_BG(), user=_User(), idem=None)
    assert len(out) == 2


async def test_merge_rejects_result_that_drops_a_source(fields_mod, monkeypatch):
    from fastapi import HTTPException

    conn = _Conn({"a": _SQ_A, "b": _SQ_B})
    _use_conn(monkeypatch, fields_mod, conn)
    req = fields_mod.FieldMergeRequest(source_field_ids=["a", "b"], name="مدموج", geometry=_SQ_A)
    with pytest.raises(HTTPException) as caught:
        await fields_mod.merge_fields(req=req, background_tasks=_BG(), user=_User(), idem=None)
    assert caught.value.status_code == 422
    assert caught.value.detail["code"] == "field_area_not_conserved"
    assert caught.value.detail["issues"] == ["source_area_not_covered"]
    assert conn.executes == []


async def test_merge_rejects_source_without_geometry(fields_mod, monkeypatch):
    from fastapi import HTTPException

    conn = _Conn({"a": _SQ_A, "b": None})
    _use_conn(monkeypatch, fields_mod, conn)
    req = fields_mod.FieldMergeRequest(source_field_ids=["a", "b"], name="مدموج", geometry=_SQ_AB)
    with pytest.raises(HTTPException) as caught:
        await fields_mod.merge_fields(req=req, background_tasks=_BG(), user=_User(), idem=None)
    assert caught.value.status_code == 422
    assert "source_geometry_missing" in caught.value.detail["issues"]
    assert conn.executes == []


async def test_merge_accepts_exact_union(fields_mod, monkeypatch):
    conn = _Conn({"a": _SQ_A, "b": _SQ_B})
    _use_conn(monkeypatch, fields_mod, conn)
    req = fields_mod.FieldMergeRequest(source_field_ids=["a", "b"], name="مدموج", geometry=_SQ_AB)
    out = await fields_mod.merge_fields(req=req, background_tasks=_BG(), user=_User(), idem=None)
    assert out["field_id"].startswith("fld_")
