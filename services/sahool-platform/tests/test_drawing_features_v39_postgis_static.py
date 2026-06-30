from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = (ROOT / "api/routers/drawing_features.py").read_text(encoding="utf-8")


def test_postgis_topology_guard_is_authoritative_before_persistence():
    assert "PostgisTopologyValidation" in ROUTER
    assert "_validate_topology_postgis" in ROUTER
    assert "ST_GeomFromGeoJSON" in ROUTER
    assert "ST_IsValid" in ROUTER
    assert "ST_IsValidReason" in ROUTER
    assert "ST_Area" in ROUTER


def test_postgis_guard_checks_parent_containment_and_zone_overlap():
    assert "ST_Covers" in ROUTER
    assert "postgis-outside-parent-field" in ROUTER
    assert "ST_Intersects" in ROUTER
    assert "ST_Intersection" in ROUTER
    assert "postgis-zone-overlap" in ROUTER
    assert "drawing_topology_invalid" in ROUTER


def test_validation_endpoint_and_persistence_merge_validation_payload():
    assert '@router.post("/api/v1/drawing-features/validate"' in ROUTER
    assert "DrawingTopologyValidateRequest" in ROUTER
    assert "_merge_validation" in ROUTER
    assert "validation_payload" in ROUTER
