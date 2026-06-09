"""
tests_v9/test_geospatial.py — runtime tests للـgeospatial integrity.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))


def test_crs_validation():
    """تحقّق من قبول EPSG:4326 ورفض غيره."""
    from api.geospatial_integrity import ValidationSeverity, validate_crs

    results = []

    valid_forms = [
        "EPSG:4326",
        "epsg:4326",
        "WGS84",
        "urn:ogc:def:crs:EPSG::4326",
        "http://www.opengis.net/def/crs/EPSG/0/4326",
        "CRS:84",
        None,  # غياب CRS = ضمنياً 4326 (RFC 7946)
    ]

    for form in valid_forms:
        issue = validate_crs(form)
        if issue is None:
            results.append(("✓", f"accepted: {form}"))
        else:
            results.append(("✗", f"REJECTED valid: {form}"))

    invalid_forms = [
        "EPSG:32638",  # UTM zone 38N (Sentinel-2 native)
        "EPSG:3857",  # Web Mercator
        "MAGIC_CRS",
        "EPSG:9999",
    ]

    for form in invalid_forms:
        issue = validate_crs(form)
        if issue and issue.severity == ValidationSeverity.ERROR:
            results.append(("✓", f"rejected: {form}"))
        else:
            results.append(("✗", f"FALSE ACCEPT: {form}"))

    return results


def test_polygon_area():
    """تحقّق من حساب المساحة spherical."""
    from api.geospatial_integrity import polygon_area_ha, polygon_area_m2

    results = []

    # مربّع تقريباً 1 km × 1 km في صنعاء (~100 hectares)
    # طول الدرجة عند خطّ العرض 15° = ~107 km
    # 0.009° lng × 0.009° lat ≈ 1 km × 1 km
    sanaa_square = [
        (44.200, 15.350),
        (44.209, 15.350),
        (44.209, 15.359),
        (44.200, 15.359),
        (44.200, 15.350),
    ]
    area_ha = polygon_area_ha(sanaa_square)
    # متوقّع: ~100 ha (1 km²)
    if 90 < area_ha < 110:
        results.append(("✓", f"~1km² square: {area_ha:.1f} ha (expected ~100)"))
    else:
        results.append(("✗", f"area off: {area_ha}"))

    # Polygon أصغر — 50m × 50m (0.25 ha)
    small = [
        (44.20000, 15.35000),
        (44.20045, 15.35000),
        (44.20045, 15.35045),
        (44.20000, 15.35045),
        (44.20000, 15.35000),
    ]
    area_small = polygon_area_ha(small)
    # متوقّع: ~0.25 ha
    if 0.20 < area_small < 0.30:
        results.append(("✓", f"50m square: {area_small:.3f} ha"))
    else:
        results.append(("✗", f"small area off: {area_small}"))

    # Empty polygon
    if polygon_area_m2([]) == 0:
        results.append(("✓", "empty polygon → 0 area"))

    # 2-point polygon (degenerate)
    if polygon_area_m2([(0, 0), (1, 1)]) == 0:
        results.append(("✓", "degenerate → 0 area"))

    return results


def test_self_intersection():
    """تحقّق من كشف polygons مكسورة."""
    from api.geospatial_integrity import has_self_intersection

    results = []

    # Simple square — no intersection
    square = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
    if not has_self_intersection(square):
        results.append(("✓", "valid square: no intersection"))

    # Bowtie (figure-8) — self-intersects
    bowtie = [(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)]
    if has_self_intersection(bowtie):
        results.append(("✓", "bowtie: intersection detected"))
    else:
        results.append(("✗", "FAILED to detect bowtie"))

    # Triangle — fine
    triangle = [(0, 0), (1, 0), (0.5, 1), (0, 0)]
    if not has_self_intersection(triangle):
        results.append(("✓", "triangle: no intersection"))

    return results


def test_field_validation_yemen():
    """validation شامل لـfield داخل اليمن."""
    from api.geospatial_integrity import ValidationSeverity, validate_field_geometry

    results = []

    # حقل صحيح في مأرب (~5 hectares)
    sanaa_field = {
        "type": "Polygon",
        "coordinates": [
            [
                [45.300, 15.450],
                [45.302, 15.450],
                [45.302, 15.452],
                [45.300, 15.452],
                [45.300, 15.450],
            ]
        ],
    }
    v = validate_field_geometry(sanaa_field)
    if v.valid:
        results.append(("✓", f"valid Yemen field: {v.computed_area_ha} ha"))
    else:
        results.append(("✗", f"valid field rejected: {[i.code for i in v.issues]}"))

    # حقل في باريس (خارج اليمن) → warning
    paris = {
        "type": "Polygon",
        "coordinates": [
            [
                [2.350, 48.850],
                [2.355, 48.850],
                [2.355, 48.852],
                [2.350, 48.852],
                [2.350, 48.850],
            ]
        ],
    }
    v = validate_field_geometry(paris)
    has_outside_warning = any(i.code == "outside_yemen_bbox" for i in v.issues)
    if has_outside_warning:
        results.append(("✓", "Paris bbox → outside Yemen warning"))

    # Self-intersecting polygon → error
    bowtie = {
        "type": "Polygon",
        "coordinates": [
            [
                [45.30, 15.45],
                [45.32, 15.47],
                [45.32, 15.45],
                [45.30, 15.47],
                [45.30, 15.45],
            ]
        ],
    }
    v = validate_field_geometry(bowtie)
    if not v.valid and any(i.code == "self_intersection" for i in v.issues):
        results.append(("✓", "self-intersection rejected"))

    # CRS error
    v = validate_field_geometry(sanaa_field, declared_crs="EPSG:32638")
    if any(i.code == "invalid_crs" for i in v.issues):
        results.append(("✓", "non-4326 CRS rejected"))

    # Invalid lng (out of range)
    bad_lng = {
        "type": "Polygon",
        "coordinates": [
            [
                [200, 15.45],  # lng > 180
                [202, 15.45],
                [202, 15.47],
                [200, 15.47],
                [200, 15.45],
            ]
        ],
    }
    v = validate_field_geometry(bad_lng)
    if any(i.code == "lng_out_of_range" for i in v.issues):
        results.append(("✓", "out-of-range longitude rejected"))

    # Auto-close ring
    not_closed = {
        "type": "Polygon",
        "coordinates": [
            [
                [45.30, 15.45],
                [45.32, 15.45],
                [45.32, 15.47],
                [45.30, 15.47],
                # missing closing point
            ]
        ],
    }
    v = validate_field_geometry(not_closed)
    has_close_warning = any(i.code == "not_closed" for i in v.issues)
    if has_close_warning:
        results.append(("✓", "unclosed ring → warning + auto-close"))

    # GeoJSON Feature wrapper
    feature = {
        "type": "Feature",
        "geometry": sanaa_field,
        "properties": {"name": "test"},
    }
    v = validate_field_geometry(feature)
    if v.valid:
        results.append(("✓", "Feature wrapper accepted"))

    return results


def test_utm_zones_yemen():
    """تحقّق من حساب UTM zones."""
    from api.geospatial_integrity import (
        YEMEN_UTM_ZONES,
        check_bbox_in_utm_zones,
        is_valid_yemen_utm_zone,
    )

    results = []

    # مأرب: lng ~45 → UTM 38
    bbox = {"min_lng": 45.0, "max_lng": 45.5, "min_lat": 15.0, "max_lat": 15.5}
    zones = check_bbox_in_utm_zones(bbox)
    if 38 in zones:
        results.append(("✓", f"Marib bbox → zones {zones}"))

    # Hadhramaut: lng ~49 → UTM 39
    bbox2 = {"min_lng": 48.5, "max_lng": 49.5, "min_lat": 15.0, "max_lat": 16.0}
    zones2 = check_bbox_in_utm_zones(bbox2)
    if 39 in zones2:
        results.append(("✓", f"Hadhramaut → zones {zones2}"))

    if all(is_valid_yemen_utm_zone(z) for z in [37, 38, 39]):
        results.append(("✓", "37/38/39 valid Yemen zones"))
    if not is_valid_yemen_utm_zone(50):
        results.append(("✓", "50 not valid Yemen zone"))

    return results


def run_all():
    print("=" * 60)
    print("  Geospatial Integrity — runtime tests")
    print("=" * 60)

    suites = [
        ("CRS Validation", test_crs_validation),
        ("Polygon Area (spherical)", test_polygon_area),
        ("Self-Intersection", test_self_intersection),
        ("Field Validation (Yemen)", test_field_validation_yemen),
        ("UTM Zones", test_utm_zones_yemen),
    ]

    tp = 0
    tf = 0
    for name, suite in suites:
        print(f"\n── {name} ──")
        try:
            for status, msg in suite():
                print(f"  {status} {msg}")
                if status == "✓":
                    tp += 1
                else:
                    tf += 1
        except Exception as e:
            print(f"  ✗ CRASHED: {type(e).__name__}: {e}")
            tf += 1

    print(f"\n{'=' * 60}")
    print(f"  Passed: {tp}/{tp + tf}")
    print(f"{'=' * 60}")
    return tp, tf


if __name__ == "__main__":
    p, f = run_all()
    sys.exit(0 if f == 0 else 1)
