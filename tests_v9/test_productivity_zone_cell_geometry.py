"""Exact spatial coverage and cells-to-area accounting for management zones."""

import pytest

from services.ai_agronomist.field_boundary_backends import mask_to_polygons
from services.ai_agronomist.productivity_zones_clustering import zones_from_ndvi_grid
from services.ai_agronomist.soil_sampling_planner import _point_in_polygons, polygon_rings

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("contour_switch", ["0", "1"])
def test_zone_preserves_missing_cell_and_separate_cluster(contour_switch, monkeypatch):
    monkeypatch.setenv("SAHOOL_BOUNDARY_CONTOUR_TRACING", contour_switch)
    grid = [
        [0.1, 0.1, 0.1, 0.1, 0.9],
        [0.1, None, 0.1, 0.1, 0.9],
        [0.1, 0.1, 0.1, 0.1, 0.9],
        [0.1, 0.9, 0.9, 0.9, 0.9],
    ]
    out = zones_from_ndvi_grid(grid, [40, 10, 50, 12], 2)
    low, high = sorted(out["zones"], key=lambda z: z["ndvi_centroid"])
    assert (low["pixel_area"], high["pixel_area"]) == (12, 7)
    assert len(low["geometry"]["coordinates"]) == 2
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            lon, lat = 40 + (c + 0.5) * 2, 12 - (r + 0.5) * 0.5
            hits = [
                z["ndvi_centroid"]
                for z in (low, high)
                if _point_in_polygons(lon, lat, polygon_rings(z["geometry"]))
            ]
            assert hits == ([] if value is None else [value])


def test_each_medium_cluster_and_disconnected_component_has_its_own_id():
    grid = [[0.1, 0.3, 0.5, 0.9, 0.1]] * 3
    zones = zones_from_ndvi_grid(grid, [0, 0, 5, 3], 4)["zones"]
    assert len(zones) == len({z["zone_id"] for z in zones}) == 5
    assert {z["zone_id"] for z in zones if z["productivity_class"] == "medium"} == {
        "pz-medium-1",
        "pz-medium-2",
    }
    assert sum(z["pixel_area"] for z in zones) == 15


def test_optional_rasterio_path_counts_cells_and_applies_minimum_size(monkeypatch):
    pytest.importorskip("rasterio")
    monkeypatch.setenv("SAHOOL_BOUNDARY_CONTOUR_TRACING", "1")
    mask = [[1, 1, 1, 0, 1], [1, 0, 1, 0, 0], [1, 1, 1, 0, 0]]
    polys = mask_to_polygons(mask, [40, 10, 50, 12], min_area_px=3)
    assert [p["pixel_area"] for p in polys] == [8]
    assert len(polys[0]["coordinates"]) == 2


def test_field_area_allocation_excludes_unobserved_cells():
    from services.ai_agronomist.field_boundary_ai import area_ha_for_bbox
    from services.ai_agronomist.productivity_zones import propose_productivity_zones

    grid = [[0.1, None, 0.9, 0.9], [0.1, 0.1, 0.9, None]]
    bbox = [44.0, 16.0, 44.01, 16.01]
    zones = propose_productivity_zones({"bbox": bbox, "zone_count": 2, "ndvi_grid": grid})[
        "productivity_zones"
    ]
    assert len(zones) == 2
    for zone in zones:
        assert zone["area_ha"] == pytest.approx(area_ha_for_bbox(bbox) * 3 / 8, abs=0.00051)
