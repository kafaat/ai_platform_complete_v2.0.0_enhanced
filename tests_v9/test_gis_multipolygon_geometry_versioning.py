from __future__ import annotations

import pytest
from api.geospatial_integrity import validate_field_geometry
from api.gis_geometry_guard import guard_field_geometry

pytestmark = pytest.mark.unit


def _poly(lon: float, lat: float) -> list[list[float]]:
    return [[lon, lat], [lon + 0.01, lat], [lon + 0.01, lat + 0.01], [lon, lat + 0.01], [lon, lat]]


def test_guard_preserves_multipolygon_parts_and_combines_bbox_area():
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [[_poly(44.95, 16.09)], [_poly(45.05, 16.19)]],
    }

    guarded = guard_field_geometry(geometry, repair=False)

    assert guarded.geometry["type"] == "MultiPolygon"
    assert len(guarded.geometry["coordinates"]) == 2
    assert guarded.bbox["min_lng"] == pytest.approx(44.95)
    assert guarded.bbox["max_lng"] == pytest.approx(45.06)
    assert guarded.bbox["min_lat"] == pytest.approx(16.09)
    assert guarded.bbox["max_lat"] == pytest.approx(16.2)
    assert guarded.area_ha > 0
    assert guarded.processing_version == "gis-guard-v2-multipolygon"


def test_guard_feature_collection_merges_polygonal_features_to_multipolygon():
    geometry = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [_poly(44.95, 16.09)]},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [_poly(45.05, 16.19)]},
            },
        ],
    }

    guarded = guard_field_geometry(geometry, repair=False)

    assert guarded.geometry["type"] == "MultiPolygon"
    assert len(guarded.geometry["coordinates"]) == 2


def test_guard_rejects_invalid_multipolygon_part():
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [
            [_poly(44.95, 16.09)],
            [[[45.0, 16.0], [45.02, 16.02], [45.0, 16.02], [45.02, 16.0], [45.0, 16.0]]],
        ],
    }

    with pytest.raises(ValueError) as exc:
        guard_field_geometry(geometry, repair=False)

    assert "part_1" in str(exc.value)


def test_validate_field_geometry_accepts_multipolygon_without_collapsing():
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [[_poly(44.95, 16.09)], [_poly(45.05, 16.19)]],
    }

    result = validate_field_geometry(geometry)

    assert result.valid
    assert result.computed_area_ha is not None and result.computed_area_ha > 0
    assert result.computed_bbox == {
        "min_lng": pytest.approx(44.95),
        "max_lng": pytest.approx(45.06),
        "min_lat": pytest.approx(16.09),
        "max_lat": pytest.approx(16.2),
    }
