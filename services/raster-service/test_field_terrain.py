"""Behavioural test: field terrain foundation returns honest computed=false envelopes.

No fabrication: without a configured/present DEM (or without a field bbox), the
terrain compute must report computed=false with a source — never a made-up number.
"""

import terrain_analysis as ta


def test_no_dem_configured_is_honest():
    r = ta.compute_field_terrain(None, [44.0, 15.0, 44.1, 15.1])
    assert r["computed"] is False
    assert r.get("source") in {"dem-not-configured", "runtime-libs-missing"}


def test_missing_dem_file_is_honest():
    r = ta.compute_field_terrain("/no/such/dem.tif", [44.0, 15.0, 44.1, 15.1])
    assert r["computed"] is False
    assert "source" in r


def test_no_bbox_is_honest_when_libs_present():
    # When rasterio is available, a missing bbox must not compute region-wide stats.
    r = ta.compute_field_terrain("/no/such/dem.tif", None)
    assert r["computed"] is False


def test_field_terrain_extent_polygon_bbox_and_ring():
    geom = {
        "type": "Polygon",
        "coordinates": [[[44.0, 15.0], [44.2, 15.0], [44.2, 15.1], [44.0, 15.1], [44.0, 15.0]]],
    }
    bbox, ring = ta.field_terrain_extent(geom)
    assert bbox == [44.0, 15.0, 44.2, 15.1]
    assert ring[0] == [44.0, 15.0] and len(ring) == 5


def test_field_terrain_extent_multipolygon_and_feature():
    feat = {
        "type": "Feature",
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [[[[44.0, 15.0], [44.1, 15.0], [44.1, 15.1], [44.0, 15.0]]]],
        },
    }
    bbox, ring = ta.field_terrain_extent(feat)
    assert bbox == [44.0, 15.0, 44.1, 15.1] and len(ring) == 4


def test_field_terrain_extent_honest_none_on_bad_geom():
    # صدق: هندسة غائبة/شاذّة/نقطة ⇒ (None, None) — لا مربّع إقليميّ مُلفَّق.
    assert ta.field_terrain_extent(None) == (None, None)
    assert ta.field_terrain_extent({"type": "Point", "coordinates": [44.0, 15.0]}) == (None, None)
    assert ta.field_terrain_extent({"type": "Polygon", "coordinates": [[[44.0, 15.0]]]}) == (
        None,
        None,
    )
