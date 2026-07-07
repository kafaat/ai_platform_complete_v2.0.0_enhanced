"""تحقّق — خطر انجراف الرشّ نحو المناطق الحسّاسة (drift geometry) منطق صرف.

- haversine/bearing صحيحان اتّجاهيّاً.
- منطقة downwind (مع الريح) معرّضة؛ upwind/بعيدة غير معرّضة.
- بلا ريح ⇒ unknown/exposed=None (لا حكم انجراف).
"""

from __future__ import annotations

from core.drift_geometry import (
    bearing_deg,
    downwind_azimuth,
    downwind_edge_point,
    exterior_ring_from_geojson,
    haversine_m,
    polygon_representative_point,
    spray_drift_risk,
    zone_drift_exposure,
)


def test_haversine_and_bearing_directions():
    # ~111.32م لكلّ 0.001° عرض عند الاستواء تقريباً.
    d = haversine_m(15.0, 45.0, 15.001, 45.0)
    assert 105 < d < 118
    assert abs(bearing_deg(15.0, 45.0, 16.0, 45.0) - 0.0) < 1  # شمالاً
    assert abs(bearing_deg(15.0, 45.0, 15.0, 46.0) - 90.0) < 1  # شرقاً


def test_downwind_azimuth_is_wind_plus_180():
    assert downwind_azimuth(315) == 135.0  # ريح شماليّة غربيّة ⇒ تنجرف جنوب-شرقاً
    assert downwind_azimuth(None) is None


def test_zone_exposed_only_when_downwind_and_near():
    # ريح من الشمال (0°) ⇒ الانجراف جنوباً (180°). منطقة جنوب الحقل قريبة ⇒ معرّضة.
    south = zone_drift_exposure(15.0, 45.0, 0.0, 14.999, 45.0, max_distance_m=200)
    assert south["exposed"] is True and south["angle_off_deg"] < 5
    # منطقة شمال الحقل (عكس الريح) ⇒ غير معرّضة.
    north = zone_drift_exposure(15.0, 45.0, 0.0, 15.001, 45.0, max_distance_m=200)
    assert north["exposed"] is False
    # جنوبيّة لكن بعيدة (>200م) ⇒ غير معرّضة.
    far = zone_drift_exposure(15.0, 45.0, 0.0, 14.99, 45.0, max_distance_m=200)
    assert far["exposed"] is False and far["distance_m"] > 200


def test_spray_drift_risk_flags_downwind_sensitive_zone():
    zones = [
        {"id": "house-1", "type": "house", "lat": 14.9992, "lon": 45.0},  # جنوب قريب
        {"id": "road-1", "type": "road", "lat": 15.001, "lon": 45.0},  # شمال (آمن)
    ]
    out = spray_drift_risk(15.0, 45.0, 0.0, zones, max_distance_m=200)
    assert out["status"] == "at_risk"
    assert [z["id"] for z in out["exposed_zones"]] == ["house-1"]
    assert out["n_zones"] == 2


def test_no_wind_is_unknown_not_a_verdict():
    out = spray_drift_risk(15.0, 45.0, None, [{"id": "x", "lat": 14.99, "lon": 45.0}])
    assert out["status"] == "unknown" and out["reason"] == "no_wind"
    assert zone_drift_exposure(15.0, 45.0, None, 14.99, 45.0)["exposed"] is None


# ── الشريحة 2: أصل الانجراف من حافّة المضلّع (لا مركز الحقل) ──────────────────

# مربّع صغير حول (15.0, 45.0): حدوده الجنوبيّة عند 14.999، الشماليّة 15.001 (GeoJSON [lon,lat]).
_SQUARE = [
    [45.0, 14.999],  # جنوب-غرب
    [45.002, 14.999],  # جنوب-شرق
    [45.002, 15.001],  # شمال-شرق
    [45.0, 15.001],  # شمال-غرب
    [45.0, 14.999],  # إغلاق
]


def test_exterior_ring_extraction_polygon_and_multipolygon():
    poly = {"type": "Polygon", "coordinates": [_SQUARE]}
    assert exterior_ring_from_geojson(poly) == _SQUARE
    multi = {"type": "MultiPolygon", "coordinates": [[_SQUARE]]}
    assert exterior_ring_from_geojson(multi) == _SQUARE
    assert exterior_ring_from_geojson({"type": "Point"}) is None
    assert exterior_ring_from_geojson(None) is None


def test_representative_point_drops_closing_vertex():
    # متوسّط 4 رؤوس (بلا رأس الإغلاق المكرّر) = مركز المربّع.
    rep = polygon_representative_point(_SQUARE)
    assert rep is not None
    assert abs(rep[0] - 15.0) < 1e-6 and abs(rep[1] - 45.001) < 1e-6


def test_downwind_edge_point_picks_leading_boundary_vertex():
    # ريح من الشمال (0°) ⇒ الانجراف جنوباً ⇒ الأصل يجب أن يكون على الحدّ الجنوبيّ (14.999).
    edge = downwind_edge_point(_SQUARE, 0.0)
    assert edge is not None and abs(edge[0] - 14.999) < 1e-6
    # ريح من الجنوب (180°) ⇒ الانجراف شمالاً ⇒ الحدّ الشماليّ (15.001).
    edge_n = downwind_edge_point(_SQUARE, 180.0)
    assert edge_n is not None and abs(edge_n[0] - 15.001) < 1e-6
    # بلا ريح/حلقة فارغة ⇒ None (لا اختلاق).
    assert downwind_edge_point(_SQUARE, None) is None
    assert downwind_edge_point([], 0.0) is None


def test_polygon_origin_is_closer_to_downwind_zone_than_center():
    # منطقة جنوب المربّع. الأصل الحافّيّ (14.999) أقرب لها من المركز (15.0) ⇒ مسافة أقصر.
    zone = [{"id": "h", "type": "house", "lat": 14.9985, "lon": 45.001}]
    poly = {"type": "Polygon", "coordinates": [_SQUARE]}
    with_poly = spray_drift_risk(15.0, 45.001, 0.0, zone, field_polygon=poly, max_distance_m=300)
    without = spray_drift_risk(15.0, 45.001, 0.0, zone, max_distance_m=300)
    assert with_poly["origin_mode"] == "polygon_boundary"
    assert without["origin_mode"] == "center"
    # المسافة من أقرب حدّ أقصر من المسافة من المركز؛ والزاوية من المركز تبقى downwind.
    assert with_poly["exposed_zones"][0]["distance_m"] < without["exposed_zones"][0]["distance_m"]
    # drift_origin (رأس الحدّ تجاه downwind) مُعلَن للعرض على الحدّ الجنوبيّ.
    assert with_poly["drift_origin"] is not None
    assert abs(with_poly["drift_origin"]["lat"] - 14.999) < 1e-6


def test_polygon_absent_keeps_center_behavior_backward_compatible():
    # بلا مضلّع: origin_mode=center والنتيجة مطابقة للشريحة 1 (متوافق للخلف).
    out = spray_drift_risk(15.0, 45.0, 0.0, [{"id": "x", "lat": 14.9992, "lon": 45.0}])
    assert out["origin_mode"] == "center" and out["status"] == "at_risk"
