from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = (ROOT / "api/routers/drawing_features.py").read_text(encoding="utf-8")


def test_drawing_features_router_exposes_crud_contract():
    migration = ROOT.parents[1] / "migrations/v230_drawing_features.sql"
    assert "CREATE TABLE IF NOT EXISTS drawing_features" in migration.read_text()
    assert "CREATE TABLE" not in ROUTER, (
        "The application role lacks schema CREATE privilege; DDL belongs to migration v230."
    )
    assert "_ensure_table" not in ROUTER, (
        "Request handlers must not restore schema bootstrap through the removed DDL helper."
    )
    manifest = (ROOT.parents[1] / "migrations/MANIFEST.txt").read_text()
    assert manifest.index("v230_drawing_features.sql") < manifest.rindex(
        "v206_rls_final_hardening.sql"
    )
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


@pytest.mark.unit
@pytest.mark.parametrize("operation", ["list", "validate", "create", "update", "delete"])
def test_drawing_endpoints_work_with_dml_only_connection(monkeypatch, operation):
    """Restore runtime _ensure_table and each route fails this DML-only witness."""
    from contextlib import asynccontextmanager
    from datetime import UTC, datetime

    from api.main import UserSchema, get_current_user
    from api.routers import drawing_features as drawing
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    tenant = "11111111-1111-1111-1111-111111111111"
    feature = {
        "id": "draw1",
        "kind": "scout-pin",
        "geometry": {"type": "Point", "coordinates": [44.1, 15.2]},
        "properties": {"fieldId": "f1"},
    }
    row = {
        "feature_id": "draw1",
        "tenant_id": tenant,
        "field_id": "f1",
        "season_id": None,
        "kind": "scout-pin",
        "workflow": None,
        "geometry": feature["geometry"],
        "properties": feature["properties"],
        "measurements": None,
        "validation": None,
        "draft": True,
        "version": 1,
        "saved_by": "42",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "deleted_at": None,
    }

    class Connection:
        async def execute(self, sql, *_args):
            raise AssertionError(f"runtime attempted DDL: {sql}")

        async def fetch(self, _sql, *_args):
            return [row]

        async def fetchrow(self, _sql, *_args):
            return row

        async def fetchval(self, _sql, *_args):
            return 1

    @asynccontextmanager
    async def connection(_user):
        yield Connection()

    async def valid_topology(*_args, **_kwargs):
        return drawing.PostgisTopologyValidation(valid=True)

    monkeypatch.setattr(drawing, "tenant_connection", connection)
    monkeypatch.setattr(drawing, "_validate_topology_postgis", valid_topology)
    app = FastAPI()
    app.include_router(drawing.router)
    app.dependency_overrides[get_current_user] = lambda: UserSchema(
        user_id="42", tenant_id=tenant, role="owner", name_ar="اختبار"
    )
    requests = {
        "list": ("GET", "/api/v1/fields/f1/drawing-features", None, 200),
        "validate": ("POST", "/api/v1/drawing-features/validate", {"feature": feature}, 200),
        "create": ("POST", "/api/v1/drawing-features", feature, 201),
        "update": ("PATCH", "/api/v1/drawing-features/draw1", {"draft": False}, 200),
        "delete": ("DELETE", "/api/v1/drawing-features/draw1", None, 200),
    }
    method, path, body, expected = requests[operation]
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.request(method, path, json=body)
    assert response.status_code == expected, response.text


@pytest.mark.unit
def test_drawing_migration_declares_owner_and_fail_closed_tenant_policy():
    sql = (ROOT.parents[1] / "migrations/v230_drawing_features.sql").read_text()
    assert "ALTER TABLE drawing_features OWNER TO CURRENT_USER;" in sql
    assert "ALTER TABLE drawing_features ENABLE ROW LEVEL SECURITY;" in sql
    assert "ALTER TABLE drawing_features FORCE ROW LEVEL SECURITY;" in sql
    predicate = "tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')"
    assert f"USING ({predicate})" in sql
    assert f"WITH CHECK ({predicate})" in sql
    assert "REVOKE ALL ON TABLE drawing_features FROM PUBLIC;" in sql
