"""field_terrain_extent must cover every part of a MultiPolygon field, not only the first."""

import pytest
import terrain_analysis as ta

pytestmark = pytest.mark.unit

_PART_A = [[44.00, 15.00], [44.01, 15.00], [44.01, 15.01], [44.00, 15.01], [44.00, 15.00]]
_PART_B = [[44.02, 15.02], [44.03, 15.02], [44.03, 15.04], [44.02, 15.04], [44.02, 15.02]]


def test_multipolygon_extent_spans_all_parts():
    geom = {"type": "MultiPolygon", "coordinates": [[_PART_A], [_PART_B]]}
    bbox, rings = ta.field_terrain_extent(geom)
    assert bbox == [44.00, 15.00, 44.03, 15.04]
    # multi-part boundary is a list of outer rings, one per part
    assert len(rings) == 2
    assert rings[0][0] == [44.00, 15.00]
    assert rings[1][0] == [44.02, 15.02]


def test_multipolygon_extent_keeps_holes_as_polygons():
    hole = [[44.002, 15.002], [44.004, 15.002], [44.004, 15.004], [44.002, 15.002]]
    geom = {
        "type": "Feature",
        "geometry": {"type": "MultiPolygon", "coordinates": [[_PART_A, hole], [_PART_B]]},
    }
    bbox, polygons = ta.field_terrain_extent(geom)
    assert bbox == [44.00, 15.00, 44.03, 15.04]
    # a holed field is returned as polygons [[exterior, hole...], ...] so the hole is kept
    assert len(polygons) == 2
    assert polygons[0][0] == _PART_A and polygons[0][1] == hole
    assert polygons[1] == [_PART_B]


def test_multipolygon_with_degenerate_part_is_rejected_not_reduced():
    # A part with a single coordinate used to be dropped silently; now the geometry is refused.
    geom = {"type": "MultiPolygon", "coordinates": [[_PART_A], [[[44.5, 15.5]]], [_PART_B]]}
    assert ta.field_terrain_extent(geom) == (None, None)


def test_mask_by_multiple_rings_keeps_every_part():
    np = pytest.importorskip("numpy")
    pytest.importorskip("rasterio")
    from rasterio.crs import CRS
    from rasterio.transform import from_origin
    from tile_render import mask_array_by_polygon

    # 30x40 grid of 0.001 deg cells covering lon 44.00..44.03, lat 15.00..15.04
    arr = np.ones((40, 30), dtype="float32")
    transform = from_origin(44.00, 15.04, 0.001, 0.001)
    out = mask_array_by_polygon(arr, transform, CRS.from_epsg(4326), [_PART_A, _PART_B])
    # a cell inside part A (bottom-left) and inside part B (top-right) stay valid
    assert np.isfinite(out[35, 5])
    assert np.isfinite(out[5, 25])
    # the gap between the parts is masked
    assert np.isnan(out[25, 15])
    # single-ring call still behaves as before
    single = mask_array_by_polygon(arr, transform, CRS.from_epsg(4326), _PART_A)
    assert np.isfinite(single[35, 5]) and np.isnan(single[5, 25])
