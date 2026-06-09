"""Tests for map_layer (ZoneOfInterest → GeoJSON FeatureCollection).
RFC 7946 compliant, categorical (not rainbow) classification, honest null handling."""
from core.spatial.map_layer import (
    zones_to_geojson, zone_to_feature, classify_value, legend_for_indicator)


class FakeZone:
    def __init__(self, polygon, value=None, reason=None, zone_id=None, area_ha=None):
        self.geometry = polygon
        self.value = value
        self.reason_ar = reason
        self.zone_id = zone_id
        self.area_ha = area_ha


class TestClassification:
    def test_categorical_bands_not_rainbow(self):
        # CRITICAL: الثقة فئة لا تدرّج وهمي
        s_low = classify_value("ndvi", 0.1)
        s_high = classify_value("ndvi", 0.8)
        assert s_low.band_name == "low"
        assert s_high.band_name == "high"

    def test_null_value_no_invented_color(self):
        # CRITICAL: قيمة None → لا اختراع لون
        s = classify_value("ndvi", None)
        assert s.band_name == "unknown"
        assert "غير متوفّر" in s.description_ar

    def test_unknown_indicator_safe_default(self):
        s = classify_value("random_indicator", 0.5)
        assert s.band_name == "unknown"

    def test_salinity_si_low_ceiling_declared(self):
        # الملوحة الطيفية قرينة سقف منخفض — يجب إعلانه صراحةً
        s = classify_value("salinity_si", 0.2)
        assert "EC مخبري" in s.description_ar


class TestGeoJsonConversion:
    def test_basic_feature_structure(self):
        z = FakeZone([(44.0, 16.0), (44.1, 16.0), (44.1, 16.1), (44.0, 16.1)],
                    value=0.6, reason="جيّد", zone_id="z1")
        f = zone_to_feature(z, indicator="ndvi")
        assert f["type"] == "Feature"
        assert f["geometry"]["type"] == "Polygon"
        # GeoJSON يتطلّب إغلاق الحلقة
        coords = f["geometry"]["coordinates"][0]
        assert coords[0] == coords[-1]

    def test_polygon_too_small_returns_none(self):
        z = FakeZone([(44.0, 16.0)])
        assert zone_to_feature(z, indicator="ndvi") is None

    def test_feature_collection_compliant(self):
        zones = [
            FakeZone([(44.0, 16.0), (44.1, 16.0), (44.1, 16.1), (44.0, 16.1)],
                    value=0.6, zone_id="z1"),
            FakeZone([(44.2, 16.0), (44.3, 16.0), (44.3, 16.1), (44.2, 16.1)],
                    value=0.2, zone_id="z2"),
        ]
        fc = zones_to_geojson(zones, indicator="ndvi")
        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) == 2

    def test_metadata_attached(self):
        fc = zones_to_geojson([], indicator="ndvi",
                              metadata={"measured_at": "2026-05-27"})
        assert fc["metadata"]["measured_at"] == "2026-05-27"

    def test_accepts_lon_lat_dict_format(self):
        z = FakeZone([{"lon": 44.0, "lat": 16.0}] * 4, value=0.5)
        f = zone_to_feature(z, indicator="ndvi")
        assert f is not None


class TestLegend:
    def test_legend_returns_all_bands(self):
        legend = legend_for_indicator("ndvi")
        assert len(legend) == 4
        assert all("color" in item and "description_ar" in item for item in legend)

    def test_unknown_indicator_empty_legend(self):
        # لا اختراع: مؤشّر غير معروف → قائمة فارغة
        assert legend_for_indicator("foo") == []
