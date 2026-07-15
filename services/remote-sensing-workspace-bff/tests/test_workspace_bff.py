import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

SPEC = importlib.util.spec_from_file_location(
    "workspace_bff_main", Path(__file__).parents[1] / "main.py"
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
client = TestClient(mod.app)


def test_health():
    assert client.get("/healthz").status_code == 200


def test_unknown_section_fails_before_upstream_calls():
    response = client.get(
        "/v1/fields/fld_a/remote-sensing-workspace",
        params={"season_id": "s1", "include": "unknown"},
        headers={"Authorization": "Bearer x", "X-Tenant-Id": "t"},
    )
    assert response.status_code == 422


def test_ground_section_is_honest_when_task_service_missing(monkeypatch):
    monkeypatch.setattr(mod, "TASK_URL", "")
    response = client.get(
        "/v1/fields/fld_a/remote-sensing-workspace",
        params={"season_id": "s1", "include": "ground"},
        headers={"Authorization": "Bearer x", "X-Tenant-Id": "t"},
    )
    assert response.status_code == 200
    assert response.json()["sections"]["ground"]["configured"] is False


def test_outcomes_is_legal_workspace_section():
    assert "outcomes" in mod._ALLOWED


def test_readyz_reports_optional_task_service():
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["task_service_configured"] is False
