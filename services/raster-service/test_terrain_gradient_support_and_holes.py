"""Terrain truth: no invented flat slope, holes are not field area, bad rings are refused.

- S-03: a DEM window without gradient support (an axis under 2 cells, or no finite
  slope cell) must return ``computed: False`` with ``dem-insufficient-gradient-support``,
  never ``computed: True`` with slope 0.0. A measured zero slope on flat ground stays valid.
- S-12: interior rings (holes) are kept by ``field_terrain_extent`` and excluded by
  ``tile_render.mask_array_by_polygon``; malformed rings are refused, not silently dropped.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
rasterio = pytest.importorskip("rasterio")

import terrain_analysis as ta  # noqa: E402
from rasterio.crs import CRS  # noqa: E402
from rasterio.transform import from_bounds, from_origin  # noqa: E402
from tile_render import mask_array_by_polygon  # noqa: E402

pytestmark = pytest.mark.unit

_REFUSAL = "dem-insufficient-gradient-support"


def _write_dem(path: Path, data, bbox) -> str:
    h, w = data.shape
    with rasterio.open(
        str(path),
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_bounds(*bbox, w, h),
        nodata=-32768.0,
    ) as dst:
        dst.write(np.asarray(data, dtype="float32"), 1)
    return str(path)


# ── S-03: gradient support ──


def test_single_row_dem_window_is_refused_not_flat(tmp_path):
    bbox = [44.0, 15.0, 44.01, 15.0001]
    dem = _write_dem(tmp_path / "row.tif", np.array([[100.0, 110.0, 120.0, 130.0]]), bbox)
    r = ta.compute_field_terrain(dem, bbox)
    assert r["computed"] is False, r
    assert r["source"] == _REFUSAL
    assert r["reason"]
    assert "slope_deg" not in r


def test_isolated_valid_pixels_without_neighbours_are_refused(tmp_path):
    bbox = [44.0, 15.0, 44.004, 15.004]
    data = np.full((4, 4), -32768.0)
    data[0, 0] = 100.0
    data[2, 2] = 120.0  # finite elevations, but no valid neighbour on either axis
    dem = _write_dem(tmp_path / "iso.tif", data, bbox)
    r = ta.compute_field_terrain(dem, bbox)
    assert r["computed"] is False, r
    assert r["source"] == _REFUSAL


def test_flat_ground_measured_zero_slope_stays_computed(tmp_path):
    bbox = [44.0, 15.0, 44.004, 15.004]
    dem = _write_dem(tmp_path / "flat.tif", np.full((4, 4), 250.0), bbox)
    r = ta.compute_field_terrain(dem, bbox)
    assert r["computed"] is True, r
    assert r["slope_deg"] == {"min": 0.0, "max": 0.0, "mean": 0.0}
    assert r["flat_pct"] == 100.0


def test_legacy_slope_aspect_refuses_single_row_and_all_nodata(tmp_path):
    bbox = [44.0, 15.0, 44.01, 15.0001]
    row = _write_dem(tmp_path / "row.tif", np.array([[1.0, 2.0, 3.0]]), bbox)
    r = ta.compute_slope_aspect(row)
    assert r["computed"] is False and r["source"] == _REFUSAL
    blank = _write_dem(tmp_path / "blank.tif", np.full((3, 3), -32768.0), [44, 15, 44.1, 15.1])
    r2 = ta.compute_slope_aspect(blank)
    assert r2["computed"] is False and r2["source"] == _REFUSAL
    flat = _write_dem(tmp_path / "flat.tif", np.full((3, 3), 5.0), [44, 15, 44.1, 15.1])
    r3 = ta.compute_slope_aspect(flat)
    assert r3["computed"] is True and r3["slope_deg"]["max"] == 0.0


# ── S-12: holes and invalid rings ──

_OUTER = [[44.00, 15.00], [44.01, 15.00], [44.01, 15.01], [44.00, 15.01], [44.00, 15.00]]
_HOLE = [[44.003, 15.003], [44.007, 15.003], [44.007, 15.007], [44.003, 15.007], [44.003, 15.003]]
_PART_B = [[44.02, 15.00], [44.03, 15.00], [44.03, 15.01], [44.02, 15.01], [44.02, 15.00]]


def _grid():
    # 10 rows x 30 cols of 0.001 deg covering lon 44.00..44.03, lat 15.00..15.01
    return np.ones((10, 30), dtype="float32"), from_origin(44.00, 15.01, 0.001, 0.001)


def test_polygon_hole_is_kept_and_masked_out():
    bbox, boundary = ta.field_terrain_extent({"type": "Polygon", "coordinates": [_OUTER, _HOLE]})
    assert bbox == [44.00, 15.00, 44.01, 15.01]
    assert boundary == [[_OUTER, _HOLE]]
    arr, transform = _grid()
    out = mask_array_by_polygon(arr, transform, CRS.from_epsg(4326), boundary)
    assert np.isnan(out[5, 5]), "hole centre must not count as field area"
    assert np.isfinite(out[1, 1]) and np.isfinite(out[8, 8]), "field ring stays valid"
    assert np.isnan(out[5, 25]), "outside the field stays masked"
    # The hole removes 4x4 cells from the 10x10 field.
    assert int(np.isfinite(out).sum()) == 100 - 16


def test_multipolygon_with_holed_part_masks_hole_and_keeps_other_part():
    geom = {"type": "MultiPolygon", "coordinates": [[_OUTER, _HOLE], [_PART_B]]}
    bbox, boundary = ta.field_terrain_extent(geom)
    assert bbox == [44.00, 15.00, 44.03, 15.01]
    arr, transform = _grid()
    out = mask_array_by_polygon(arr, transform, CRS.from_epsg(4326), boundary)
    assert np.isnan(out[5, 5])
    assert np.isfinite(out[1, 1])
    assert np.isfinite(out[5, 25]), "second part is field area"
    assert np.isnan(out[5, 15]), "gap between parts is masked"
    assert int(np.isfinite(out).sum()) == (100 - 16) + 100


def test_terrain_on_holed_field_excludes_hole_elevations(tmp_path):
    # Hole region carries a 900 m spike; it must not enter the field's elevation stats.
    bbox = [44.00, 15.00, 44.01, 15.01]
    data = np.full((10, 10), 100.0)
    data[3:7, 3:7] = 900.0
    dem = _write_dem(tmp_path / "holed.tif", data, bbox)
    _bbox, boundary = ta.field_terrain_extent({"type": "Polygon", "coordinates": [_OUTER, _HOLE]})
    r = ta.compute_field_terrain(dem, bbox, poly=boundary)
    assert r["computed"] is True, r
    assert r["elevation_m"]["max"] == 100.0


@pytest.mark.parametrize(
    "coords",
    [
        [[[44.0, 15.0], [44.1, 15.0], [44.0, 15.0]]],  # ring under 4 coordinates
        [_OUTER, [[44.003, 15.003], [44.004, 15.003], [44.003, 15.003]]],  # short hole
        [[[44.0, 15.0], [44.1, float("nan")], [44.1, 15.1], [44.0, 15.0]]],  # NaN
        [[[44.0, 15.0], [44.1, math.inf], [44.1, 15.1], [44.0, 15.0]]],  # Inf
        [[[44.0, 15.0], [44.1], [44.1, 15.1], [44.0, 15.1], [44.0, 15.0]]],  # short point
    ],
)
def test_invalid_rings_are_refused_not_reduced(coords):
    assert ta.field_terrain_extent({"type": "Polygon", "coordinates": coords}) == (None, None)


def test_compute_field_terrain_refuses_invalid_boundary(tmp_path):
    bbox = [44.00, 15.00, 44.01, 15.01]
    dem = _write_dem(tmp_path / "d.tif", np.full((10, 10), 100.0), bbox)
    bad = [[44.0, 15.0], [44.01, 15.0], [44.0, 15.0]]
    r = ta.compute_field_terrain(dem, bbox, poly=bad)
    assert r["computed"] is False
    assert r["source"] == "field-geometry-invalid"


def test_single_ring_boundary_still_works():
    bbox, ring = ta.field_terrain_extent({"type": "Polygon", "coordinates": [_OUTER]})
    assert ring == _OUTER
    arr, transform = _grid()
    out = mask_array_by_polygon(arr, transform, CRS.from_epsg(4326), ring)
    assert int(np.isfinite(out).sum()) == 100
