"""Anomaly ground-scouting tasks on field-management-service — unit contract (W1-20, no database).

The stored behaviour (one row per key and per anomaly, replay, concurrency, RLS, the v282 indexes)
is measured on PostgreSQL by tests_v9/test_field_task_scouting_anomaly_live_pg.py. Here: the
routes exist on the owner, they take the service-token guard (the gateway token alone opens
nothing), the Idempotency-Key is required, the request is references only, its digest is stable,
and each store outcome maps to its status. The store is stubbed at the store-function level.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.append(str(SERVICE_DIR))

pytest.importorskip("fastapi")

import fm_scouting_tasks as fst  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TENANT = "11111111-1111-4111-8111-111111111111"
TOKEN = "unit-agent-token"
KEY = "a" * 64
PATH = "/internal/field-tasks/scouting"
BODY = {
    "anomaly_ref": "urn:sahool:anomaly:anomaly_0123456789abcdef01234567",
    "field_id": "fld_demo",
    "season_id": "sea_demo",
    "geometry_ref": None,
    "priority": "high",
    "verification_deadline": "2026-11-17T09:00:00+00:00",
    "reason_codes": ["canonical_observation_baseline", "direction:decline"],
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setenv("FIELD_TASKS_SERVICE_TOKEN", "gateway-token")
    for name in (
        "FIELD_SERVICE_ALLOWED_CALLERS",
        "FIELD_SERVICE_TENANT_ASSERTION_KEY",
        "FIELD_SERVICE_ASSERTION_REDIS_URL",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    spec = importlib.util.spec_from_file_location("fm_main_scouting_unit", SERVICE_DIR / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return TestClient(mod.app)


def _headers(**extra):
    return {
        "X-Agent-Token": TOKEN,
        "X-Tenant-Id": TENANT,
        "X-Service-Name": "vegetation-analysis-service",
        "Idempotency-Key": KEY,
        **extra,
    }


def _stub_store(monkeypatch, outcome):
    """Replace the store functions (not the connection): `outcome` returns or raises."""
    seen = []

    async def in_tx(connect, tenant, work):
        return await work(None)

    async def create(conn, tenant, req, key, digest, service):
        seen.append((tenant, req, key, digest, service))
        return outcome()

    monkeypatch.setattr(fst, "_in_tenant_tx", in_tx)
    monkeypatch.setattr(fst, "store_create", create)
    return seen


def _task(task_id="5b0c3a4e-1d2f-4a5b-8c6d-7e8f9a0b1c2d"):
    return fst.task_view({"task_id": task_id, "reason_codes": '["direction:decline"]'})


def test_the_owner_serves_post_and_get_scouting_tasks(client):
    routes = {(m, r.path) for r in client.app.routes for m in getattr(r, "methods", ())}
    assert ("POST", PATH) in routes, "field-management-service must serve POST scouting tasks"
    assert ("GET", PATH) in routes, "field-management-service must serve GET scouting tasks"


def test_service_token_is_required_and_the_gateway_token_opens_nothing(client):
    no_token = {k: v for k, v in _headers().items() if k != "X-Agent-Token"}
    assert client.post(PATH, json=BODY, headers=no_token).status_code == 401, "no token ⇒ 401"
    gateway = {**no_token, "X-Field-Tasks-Token": "gateway-token", "X-User-Id": "7"}
    assert client.post(PATH, json=BODY, headers=gateway).status_code == 401, (
        "the gateway's X-Field-Tasks-Token must not open a service-to-service route"
    )
    assert client.get(PATH, params={"field_id": "fld_demo"}, headers=gateway).status_code == 401, (
        "the list is service-token only too"
    )


def test_the_tenant_must_be_a_uuid_and_the_key_is_required(client, monkeypatch):
    seen = _stub_store(monkeypatch, lambda: (_task(), False))
    missing = {k: v for k, v in _headers().items() if k != "Idempotency-Key"}
    assert client.post(PATH, json=BODY, headers=missing).status_code == 400, "no key ⇒ 400"
    short = _headers(**{"Idempotency-Key": "short"})
    assert client.post(PATH, json=BODY, headers=short).status_code == 400, "short key ⇒ 400"
    bad_tenant = _headers(**{"X-Tenant-Id": "tenant-1"})
    assert client.post(PATH, json=BODY, headers=bad_tenant).status_code == 400, "tenant ⇒ UUID"
    assert seen == [], "nothing reaches the store before the request is valid"


def test_the_request_carries_references_only(client, monkeypatch):
    _stub_store(monkeypatch, lambda: (_task(), False))
    for extra in ({"suspected_condition": "water_stress"}, {"diagnosis": "rust"}):
        response = client.post(PATH, json={**BODY, **extra}, headers=_headers())
        assert response.status_code == 422, f"a diagnosis field must be refused: {extra}"
    bad_ref = {**BODY, "anomaly_ref": "anomaly_1"}
    assert client.post(PATH, json=bad_ref, headers=_headers()).status_code == 422, (
        "an anomaly reference is a urn:sahool:anomaly: URN"
    )
    bad_priority = {**BODY, "priority": "urgent"}
    assert client.post(PATH, json=bad_priority, headers=_headers()).status_code == 422, (
        "only the anomaly engine's severities are accepted"
    )


def test_a_new_task_is_201_with_a_task_ref_and_a_replay_is_200(client, monkeypatch):
    seen = _stub_store(monkeypatch, lambda: (_task(), False))
    created = client.post(PATH, json=BODY, headers=_headers())
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["persisted"] is True and data["replayed"] is False, data
    assert data["task_ref"] == "urn:sahool:task:" + data["task_id"], data
    tenant, req, key, digest, service = seen[0]
    assert (tenant, key, service) == (TENANT, KEY, "vegetation-analysis-service"), seen[0]
    assert digest == fst.request_digest(req), "the stored digest is the request's"

    _stub_store(monkeypatch, lambda: (_task(), True))
    replay = client.post(PATH, json=BODY, headers=_headers())
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True, replay.json()
    assert replay.json()["task_id"] == data["task_id"], "a replay names the same task"


@pytest.mark.parametrize("season_id", ["2026/2027", "موسم 2026", "sea_demo"])
def test_any_season_id_vegetation_accepts_is_accepted(client, monkeypatch, season_id):
    """Vegetation's DetectRequest takes any 1-128 character season_id; a stricter pattern here
    made every verification of such an anomaly fail with 422 (review LOW, W1-20)."""
    seen = _stub_store(monkeypatch, lambda: (_task(), False))
    response = client.post(PATH, json={**BODY, "season_id": season_id}, headers=_headers())
    assert response.status_code == 201, (season_id, response.text)
    assert seen[0][1].season_id == season_id, "the season reaches the store unchanged"


@pytest.mark.parametrize("season_id", ["", "sea\ndemo", "s" * 129])
def test_an_empty_control_or_overlong_season_id_is_refused(client, monkeypatch, season_id):
    seen = _stub_store(monkeypatch, lambda: (_task(), False))
    response = client.post(PATH, json={**BODY, "season_id": season_id}, headers=_headers())
    assert response.status_code == 422, (season_id, response.text)
    assert seen == [], "an invalid season never reaches the store"


@pytest.mark.parametrize(
    ("raised", "status"),
    [
        (fst.IdempotencyConflict("idempotency_key_reused_with_different_request"), 409),
        (fst.IdempotencyConflict("anomaly_already_has_task", _task()), 409),
        (fst.FieldNotFound("fld_demo"), 404),
        (type("UniqueViolation", (Exception,), {"sqlstate": "23505"})(), 409),
        (RuntimeError("connection refused"), 503),
    ],
)
def test_store_outcomes_map_to_statuses(client, monkeypatch, raised, status):
    def outcome():
        raise raised

    _stub_store(monkeypatch, outcome)
    response = client.post(PATH, json=BODY, headers=_headers())
    assert response.status_code == status, (raised, response.text)


def test_an_unconfigured_database_is_503_not_a_fallback(client):
    response = client.post(PATH, json=BODY, headers=_headers())
    assert response.status_code == 503, "DATABASE_URL unset ⇒ 503, never a synthetic task"


def test_the_digest_binds_the_request_not_its_spelling():
    one = fst.ScoutingTaskRequest(**BODY)
    same_instant = fst.ScoutingTaskRequest(
        **{**BODY, "verification_deadline": "2026-11-17T12:00:00+03:00"}
    )
    other = fst.ScoutingTaskRequest(**{**BODY, "priority": "low"})
    assert fst.request_digest(one) == fst.request_digest(same_instant), (
        "the same deadline written with another offset is the same request"
    )
    assert fst.request_digest(one) != fst.request_digest(other), "another body ⇒ another digest"


def test_severity_maps_to_the_platforms_ascending_priority():
    order = [fst.SEVERITY_PRIORITY[s] for s in ("critical", "high", "medium", "low", "info")]
    assert order == [1, 2, 3, 4, 5], "1 is the most urgent (the platform sorts priority ASC)"


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "missing-separator",
        "|bad-uuid",
        f"|{TENANT}|extra",
        f"2026-01-01T12:00:00|{TENANT}",
        f"0001-01-01T00:00:00+12:00|{TENANT}",
    ],
)
def test_invalid_page_cursors_are_client_errors_before_db_access(client, cursor):
    response = client.get(
        PATH, params={"field_id": "fld_demo", "cursor": cursor}, headers=_headers()
    )
    assert response.status_code == 400, response.text


@pytest.mark.parametrize("limit", [0, 201])
def test_scouting_page_limit_is_bounded(client, limit):
    response = client.get(PATH, params={"field_id": "fld_demo", "limit": limit}, headers=_headers())
    assert response.status_code == 422
