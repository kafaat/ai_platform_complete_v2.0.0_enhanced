from copy import deepcopy

import pytest
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

from services.ai_agronomist.productivity_zones import propose_productivity_zones

pytestmark = pytest.mark.unit
GRID = [[0.1, 0.1, 0.9, 0.9]] * 4


def pack(affine, bbox, crs="EPSG:4326"):
    return {
        "ndvi_grid": GRID,
        "grid_metadata": {
            "ndvi": {
                "grid_identity": {
                    "transform": affine,
                    "crs": crs,
                    "geometry_revision": 1,
                    "rows": 4,
                    "cols": 4,
                },
                "bbox": bbox,
                "scene_id": "S2",
                "acquisition_date": "2026-05-01",
            }
        },
    }


def all_zones(result):
    return unary_union([shape(z["geometry"]) for z in result["productivity_zones"]])


def test_raster_metadata_wgs84_without_caller_extent_and_disjoint_request():
    extent = [44, 15, 44.04, 15.04]
    source = pack([0.01, 0, 44, 0, -0.01, 15.04], extent)
    result = propose_productivity_zones({"zone_count": 2}, evidence_context=source)
    assert result["grid_bbox"] == extent
    assert result["grid_bbox_source"] == "grid_metadata.ndvi.bbox_and_grid_identity"
    assert all_zones(result).bounds == pytest.approx(extent)
    for prop, value in [("bbox", [50, 20, 50.04, 20.04]), ("bbox", [44, 15, 44.04, 15.04])]:
        ev = deepcopy(source)
        if value == extent:
            ev["grid_metadata"]["ndvi"]["bbox"] = [41, 15, 41.04, 15.04]
        res = propose_productivity_zones({prop: value, "zone_count": 2}, evidence_context=ev)
        assert res["productivity_zones"] == []
        assert res["reason_codes"][0] in ("ndvi_grid_outside_field", "ndvi_bbox_affine_mismatch")


def test_utm_38n_yemen_projected_cell_edges_are_reprojected():
    # Reference corners independently evaluated with PROJ's EPSG:32638 transformation.
    extent = [45, 16.280472, 45.000374, 16.280833]
    source = pack([10, 0, 500000, 0, -10, 1800000], extent, "EPSG:32638")
    result = propose_productivity_zones({"zone_count": 2}, evidence_context=source)
    assert len(result["productivity_zones"]) == 2
    assert all_zones(result).bounds == pytest.approx(
        [45, 16.28047171585, 45.00037438864, 16.28083332316], abs=1e-9
    )
    left = next(z for z in result["productivity_zones"] if z["productivity_class"] == "low")
    assert shape(left["geometry"]).bounds[2] == pytest.approx(45.00018719432, abs=1e-9)
    assert left["area_ha"] == pytest.approx(0.08, abs=0.002)


def test_rotation_preserved_with_hole_and_full_field_clipping():
    # 4x4 affine footprint is a parallelogram with one sheared axis.
    source = pack([0.01, 0.005, 44, 0, -0.01, 16.04], [44, 16, 44.06, 16.04])
    rotated = propose_productivity_zones({"zone_count": 2}, evidence_context=source)
    assert all_zones(rotated).area == pytest.approx(0.0016)
    assert all_zones(rotated).bounds == pytest.approx([44, 16, 44.06, 16.04])
    shell = [[44.01, 16.037], [44.031, 16.037], [44.05, 16.004], [44.025, 16.004], [44.01, 16.037]]
    hole = [
        [44.026, 16.023],
        [44.027, 16.023],
        [44.027, 16.024],
        [44.026, 16.024],
        [44.026, 16.023],
    ]
    boundary = {"type": "Polygon", "coordinates": [shell, hole]}
    result = propose_productivity_zones(
        {"zone_count": 2, "boundary": boundary}, evidence_context=source
    )
    union = all_zones(result)
    assert union.area == pytest.approx(Polygon(shell, [hole]).area, abs=1e-11)
    assert union.difference(shape(boundary)).area < 1e-15


def test_legacy_evidence_cannot_inherit_identity_from_caller():
    data = pack([0.01, 0, 44, 0, -0.01, 15.04], [44, 15, 44.04, 15.04])
    params = {**data, "bbox": [50, 19, 50.04, 19.04], "zone_count": 2}
    result = propose_productivity_zones(params, evidence_context={"ndvi_grid": GRID})
    assert result["grid_bbox_source"] == "caller_extent_for_legacy_evidence"
    assert "caller_grid_georeferencing_required" in result["limitations"]


@pytest.mark.parametrize("grid", [[[]], [[0.2, 0.8], [0.1]]])
def test_ragged_grid_never_gets_an_affine_or_a_zone(grid):
    out = propose_productivity_zones({"bbox": [44, 15, 45, 16], "ndvi_grid": grid})
    assert out["reason_codes"] == ["invalid_ndvi_grid_shape"]
