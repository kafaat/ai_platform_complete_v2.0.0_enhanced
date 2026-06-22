"""خدمة CRS الموحّدة (shared/gis/crs_service) — اختبار وحدة نقيّ.

يثبت: تطبيع GeoJSON إلى EPSG:4326 (مع نزع عضو crs ورفض CRS غير 4326)،
وتحويل lon/lat إلى Web Mercator (EPSG:3857) بالصيغة الكرويّة المضمَّنة.
دوالّ نقيّة بلا قاعدة بيانات أو خدمات.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.gis.crs_service import (  # noqa: E402
    WEB_MERCATOR,
    WGS84,
    normalize_to_wgs84,
    transform_to_map_projection,
)

# مضلّع حقل بسيط حول صنعاء (lon/lat).
_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [[44.33, 16.79], [44.34, 16.79], [44.34, 16.80], [44.33, 16.80], [44.33, 16.79]]
    ],
}


class TestConstants:
    def test_constants(self):
        assert WGS84 == "EPSG:4326"
        assert WEB_MERCATOR == "EPSG:3857"


class TestNormalize:
    def test_already_4326_passthrough(self):
        out = normalize_to_wgs84(_POLYGON)
        assert out["type"] == "Polygon"
        assert out["coordinates"] == _POLYGON["coordinates"]
        assert "crs" not in out

    def test_strips_legacy_crs_member_4326(self):
        geo = {
            **_POLYGON,
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        }
        out = normalize_to_wgs84(geo)
        assert "crs" not in out
        assert out["coordinates"] == _POLYGON["coordinates"]

    def test_does_not_mutate_input(self):
        geo = {**_POLYGON, "crs": {"type": "name", "properties": {"name": "EPSG:4326"}}}
        _ = normalize_to_wgs84(geo)
        assert "crs" in geo  # المدخل سليم

    def test_rejects_non_4326_declared_crs(self):
        geo = {
            **_POLYGON,
            "crs": {"type": "name", "properties": {"name": "EPSG:32638"}},
        }
        with pytest.raises(ValueError, match="non-WGS84"):
            normalize_to_wgs84(geo)

    def test_rejects_non_dict(self):
        with pytest.raises(ValueError):
            normalize_to_wgs84([1, 2, 3])  # type: ignore[arg-type]

    def test_nested_crs_stripped_in_featurecollection(self):
        fc = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": dict(_POLYGON),
                }
            ],
        }
        out = normalize_to_wgs84(fc)
        assert "crs" not in out


class TestTransform:
    def test_point_origin(self):
        out = transform_to_map_projection({"type": "Point", "coordinates": [0.0, 0.0]})
        x, y = out["coordinates"]
        assert math.isclose(x, 0.0, abs_tol=1e-6)
        assert math.isclose(y, 0.0, abs_tol=1e-6)
        assert out["crs"]["properties"]["name"] == WEB_MERCATOR

    def test_known_mercator_value(self):
        # القيمة المرجعيّة المعروفة: lon=180 → x = π·R = نصف امتداد العالم.
        out = transform_to_map_projection({"type": "Point", "coordinates": [180.0, 0.0]})
        x, _y = out["coordinates"]
        assert math.isclose(x, math.pi * 6378137.0, rel_tol=1e-9)

    def test_lat_clamped_at_poles(self):
        out = transform_to_map_projection({"type": "Point", "coordinates": [0.0, 89.0]})
        _x, y = out["coordinates"]
        # القصّ عند ‎±85.05° يجعل y منتهياً لا لانهائيّاً.
        assert math.isfinite(y)

    def test_polygon_shape_preserved(self):
        out = transform_to_map_projection(_POLYGON)
        ring = out["coordinates"][0]
        assert len(ring) == len(_POLYGON["coordinates"][0])
        assert ring[0] == ring[-1]  # الحلقة مغلقة
        # شمال صنعاء ⇒ y موجب (نصف الكرة الشماليّ).
        assert all(pt[1] > 0 for pt in ring)

    def test_feature_transformed(self):
        feat = {"type": "Feature", "properties": {"id": 1}, "geometry": dict(_POLYGON)}
        out = transform_to_map_projection(feat)
        assert out["type"] == "Feature"
        assert out["geometry"]["coordinates"][0][0][0] != _POLYGON["coordinates"][0][0][0]

    def test_rejects_unsupported_target(self):
        with pytest.raises(ValueError, match="unsupported target"):
            transform_to_map_projection(_POLYGON, target="EPSG:32638")

    def test_rejects_non_4326_source(self):
        geo = {**_POLYGON, "crs": {"type": "name", "properties": {"name": "EPSG:32638"}}}
        with pytest.raises(ValueError, match="non-WGS84"):
            transform_to_map_projection(geo)
