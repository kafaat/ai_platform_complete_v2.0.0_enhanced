"""Regression tests for the agricultural polygon tool's public input boundary."""

import math

import pytest
from core.agri_tools.registry import run_tool
from core.agri_tools.tools.polygon_area import compute

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "point",
    [
        [181, 15],
        [-181, 15],
        [44, 91],
        [44, -91],
        [float("nan"), 15],
        [44, float("inf")],
        [True, 15],
        [44, None],
        [10**400, 15],
        "44",
        [44],
        [44, 15, 100],
    ],
)
def test_agri_polygon_invalid_coordinates_raise_value_error(point):
    with pytest.raises(ValueError):
        run_tool("polygon_area", {"coordinates": [point, [44.01, 15], [44, 15.01]]})


@pytest.mark.parametrize("coordinates", [42, {}, "abc"])
def test_agri_polygon_invalid_ring_type_raises_value_error(coordinates):
    with pytest.raises(ValueError):
        run_tool("polygon_area", {"coordinates": coordinates})


def test_agri_polygon_ring_with_only_two_distinct_vertices_is_rejected():
    with pytest.raises(ValueError):
        compute([[44, 15], [44.01, 15], [44, 15], [44.01, 15]])


@pytest.mark.parametrize("reverse", [False, True])
def test_agri_polygon_small_field_crossing_antimeridian_has_local_area(reverse):
    ring = [[179.995, 15], [-179.995, 15], [-179.995, 15.01], [179.995, 15.01]]
    reference = [[44, 15], [44.01, 15], [44.01, 15.01], [44, 15.01]]
    if reverse:
        ring.reverse()
    actual = compute(ring)
    expected = compute(reference)
    assert math.isclose(actual["area_m2"], expected["area_m2"], rel_tol=1e-6)
    assert math.isclose(actual["perimeter_m"], expected["perimeter_m"], rel_tol=1e-6)


def test_agri_polygon_valid_numeric_strings_remain_supported():
    ring = [[44, 15], [44.01, 15], [44, 15.01]]
    assert compute([[str(x), str(y)] for x, y in ring]) == compute(ring)
