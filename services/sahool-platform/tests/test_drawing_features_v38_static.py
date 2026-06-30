from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = (ROOT / "api/routers/drawing_features.py").read_text(encoding="utf-8")


def test_drawing_features_router_exposes_crud_contract():
    assert "CREATE TABLE IF NOT EXISTS drawing_features" in ROUTER
    assert '@router.get("/api/v1/fields/{field_id}/drawing-features"' in ROUTER
    assert '@router.post("/api/v1/drawing-features"' in ROUTER
    assert '@router.patch("/api/v1/drawing-features/{feature_id}"' in ROUTER
    assert '@router.delete("/api/v1/drawing-features/{feature_id}"' in ROUTER


def test_drawing_features_router_is_tenant_scoped_and_permissioned():
    assert "tenant_id = $1::uuid" in ROUTER
    assert "tenant_id = $2::uuid" in ROUTER
    assert "require_permission(Permission.FIELD_VIEW)" in ROUTER
    assert "require_permission(Permission.FIELD_EDIT)" in ROUTER
    assert "_assert_field_owner" in ROUTER


def test_drawing_features_preserves_agricultural_metadata():
    for token in ["fieldId", "seasonId", "workflow", "design-pivot", "measurements", "validation"]:
        assert token in ROUTER
