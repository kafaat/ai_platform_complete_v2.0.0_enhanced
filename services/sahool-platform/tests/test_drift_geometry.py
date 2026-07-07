"""تحقّق — خطر انجراف الرشّ نحو المناطق الحسّاسة (drift geometry) منطق صرف.

- haversine/bearing صحيحان اتّجاهيّاً.
- منطقة downwind (مع الريح) معرّضة؛ upwind/بعيدة غير معرّضة.
- بلا ريح ⇒ unknown/exposed=None (لا حكم انجراف).
"""

from __future__ import annotations

from core.drift_geometry import (
    bearing_deg,
    downwind_azimuth,
    haversine_m,
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
