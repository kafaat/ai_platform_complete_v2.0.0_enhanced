import pytest
from api.gis_geometry_guard import guard_field_geometry
from api.pivot_geometry import PivotSpec, generate_pivot_polygon

pytestmark = pytest.mark.unit


def test_guard_closes_and_deduplicates_polygon():
    raw = {
        "type": "Polygon",
        "coordinates": [
            [[44.0, 15.0], [44.01, 15.0], [44.01, 15.01], [44.01, 15.01], [44.0, 15.01]]
        ],
    }
    guarded = guard_field_geometry(raw)
    ring = guarded.geometry["coordinates"][0]
    assert ring[0] == ring[-1]
    assert [44.01, 15.01] in ring
    assert guarded.area_ha > 0


def test_guard_rejects_self_intersection():
    bow_tie = {
        "type": "Polygon",
        "coordinates": [[[44.0, 15.0], [44.02, 15.02], [44.0, 15.02], [44.02, 15.0], [44.0, 15.0]]],
    }
    try:
        guard_field_geometry(bow_tie, repair=False)
    except ValueError as exc:
        assert "self_intersection" in str(exc)
    else:
        raise AssertionError("self-intersecting polygon must be rejected")


def test_pivot_polygon_is_canonical_and_valid():
    polygon = generate_pivot_polygon(
        PivotSpec(center_lon=44.0, center_lat=15.0, radius_m=500, vertices=48)
    )
    assert polygon["type"] == "Polygon"
    ring = polygon["coordinates"][0]
    assert ring[0] == ring[-1]
    assert len(ring) >= 48
    guarded = guard_field_geometry(polygon, repair=False)
    assert guarded.area_ha > 70
