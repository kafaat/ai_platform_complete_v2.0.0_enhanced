"""Tests for field_bundle: aggregates all spatial layers into a single structured response.
The bundle is the contract between core and UI - honest about missing pieces, no invented defaults."""
from core.spatial.field_bundle import (
    build_bundle, png_to_data_uri,
    TimelineSnapshot, SamplePoint, SensorLocation, ActivityMarker)


class TestBundleBuilding:
    def test_minimal_bundle_warns_about_missing_layers(self):
        # لا حدود، لا zones، لا raster → تحذير صريح
        b = build_bundle(field_id="f1")
        assert b.field_id == "f1"
        assert b.boundary_geojson is None
        assert b.raster_png_base64 is None
        assert len(b.warnings_ar) > 0   # يجب أن يحذّر

    def test_boundary_converted_to_polygon_feature(self):
        b = build_bundle(field_id="f1",
            boundary_polygon=[(44.0, 16.0), (44.1, 16.0),
                              (44.1, 16.1), (44.0, 16.1)])
        assert b.boundary_geojson is not None
        assert b.boundary_geojson["type"] == "Feature"
        assert b.boundary_geojson["geometry"]["type"] == "Polygon"
        # إغلاق الحلقة (RFC 7946)
        coords = b.boundary_geojson["geometry"]["coordinates"][0]
        assert coords[0] == coords[-1]

    def test_accepts_dict_polygon_format(self):
        b = build_bundle(field_id="f1",
            boundary_polygon=[{"lon": 44.0, "lat": 16.0},
                              {"lon": 44.1, "lat": 16.0},
                              {"lon": 44.1, "lat": 16.1}])
        assert b.boundary_geojson is not None

    def test_insufficient_points_warned_not_invented(self):
        # نقطتان فقط → تحذير، لا اختراع نقاط
        b = build_bundle(field_id="f1",
            boundary_polygon=[(44.0, 16.0), (44.1, 16.0)])
        assert b.boundary_geojson is None
        assert any("غير كافية" in w for w in b.warnings_ar)


class TestPngDataUri:
    def test_png_to_valid_data_uri(self):
        # PNG header
        png = b"\x89PNG\r\n\x1a\n" + b"fake_data"
        uri = png_to_data_uri(png)
        assert uri.startswith("data:image/png;base64,")
        # يجب أن يكون base64 صالحاً
        import base64
        b64_part = uri.split(",")[1]
        decoded = base64.b64decode(b64_part)
        assert decoded == png

    def test_empty_returns_empty(self):
        # لا اختراع — bytes فارغة → سلسلة فارغة
        assert png_to_data_uri(b"") == ""
        assert png_to_data_uri(None) == ""


class TestResponseFormat:
    def test_response_has_all_required_fields(self):
        b = build_bundle(field_id="f1")
        resp = b.to_response()
        required = ["field_id", "boundary", "zones", "raster", "timeline",
                    "sample_points", "sensors", "activities", "legend",
                    "warnings_ar"]
        for f in required:
            assert f in resp, f"حقل ناقص: {f}"

    def test_missing_pieces_become_explicit_nulls(self):
        # CRITICAL: لا قيم وهمية — الناقص = null أو [] صريح
        b = build_bundle(field_id="f1")
        resp = b.to_response()
        assert resp["raster"] is None     # لا اختراع
        assert resp["boundary"] is None
        assert resp["timeline"] == []     # قائمة فارغة، لا None غامض
        assert resp["sample_points"] == []

    def test_timeline_serialized_correctly(self):
        snaps = [
            TimelineSnapshot("s1", "2026-05-20", "ndvi", 90.0, 10.0, "sentinel2", True),
            TimelineSnapshot("s2", "2026-05-27", "ndvi", 95.0, 5.0, "sentinel2", True),
        ]
        b = build_bundle(field_id="f1", timeline=snaps)
        resp = b.to_response()
        assert len(resp["timeline"]) == 2
        assert resp["timeline"][0]["captured_at"] == "2026-05-20"

    def test_sample_points_with_coords(self):
        # نقطة عيّنة بإحداثيات — لخريطة العيّنات
        sp = SamplePoint(1, 44.05, 16.05, "salinity", "pending", "2026-05-25")
        b = build_bundle(field_id="f1", sample_points=[sp])
        resp = b.to_response()
        assert resp["sample_points"][0]["lon"] == 44.05
        assert resp["sample_points"][0]["purpose"] == "salinity"

    def test_sensor_location_carries_confidence(self):
        # الحسّاسات: confidence=medium دائماً (مبدأ سهول)
        s = SensorLocation("dev01", "soil_moisture", 44.05, 16.05,
                          35.5, "2026-05-27T10:00", "medium")
        b = build_bundle(field_id="f1", sensors=[s])
        resp = b.to_response()
        assert resp["sensors"][0]["confidence"] == "medium"
