"""Task irrigation observations are evidence, never execution or ledger mutations.

HTTP tests use the real router/model/service with a SQL fake. They demonstrate
boundary behavior, not PostgreSQL RLS/locking or device execution.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import types
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from api.api_models import ObservationRequest, TaskListResponse, TaskSummary, TaskUpdateRequest
from core.authorization import Permission, has_permission
from core.canonical_schemas import UserRole, UserSchema
from core.offline_first import OfflineQueue
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit
TENANT = "11111111-1111-4111-8111-111111111111"
OTHER_TENANT = "22222222-2222-4222-8222-222222222222"
EXECUTION = "33333333-3333-4333-8333-333333333333"
OBSERVATION = "44444444-4444-4444-8444-444444444444"
URL = "/api/v1/observations"
GET_URL = "/api/v1/tasks?irrigation_task_id=task-1"


def _body(**changes):
    body = {
        "observation_id": OBSERVATION,
        "execution_id": EXECUTION,
        "source": "farmer_task",
        "outcome": "irrigated",
        "occurred_at": "2026-01-01T10:00:00Z",
        "quantity_method": "declared_volume",
        "volume_m3": 3000,
        "irrigated_area_ha": 50,
        "notes": "Farmer declaration, not a meter receipt",
    }
    body.update(changes)
    return {"task_id": "task-1", "irrigation_observation": body}


def _user(role=UserRole.MANAGER):
    return UserSchema(user_id="actor-1", tenant_id=TENANT, role=role, name_ar="مدير")


class ObservationConn:
    def __init__(self):
        self.task = {
            "task_id": "task-1",
            "tenant_id": TENANT,
            "field_id": "field-1",
            "task_type": "irrigation",
            "status": "pending",
        }
        self.execution = {
            "execution_id": EXECUTION,
            "tenant_id": TENANT,
            "field_id": "field-1",
            "state": "started",
        }
        self.events = {}
        self.writes = []
        self.queries = []

    async def fetchrow(self, sql, *args):
        self.queries.append((sql, args))
        if "INSERT INTO irrigation_manual_execution_events" in sql:
            self.writes.append((sql, args))
            event_id, tenant, execution, state, actor, payload, digest = args
            event_id = str(event_id)
            if event_id in self.events:
                return None
            assert state == self.execution["state"]
            data = json.loads(payload)
            self.events[event_id] = {"tenant_id": str(tenant), "payload": data}
            return {"payload": json.dumps(data)}
        if "FROM field_tasks" in sql:
            assert "tenant_id" in sql and "FOR SHARE" in sql
            return (
                self.task
                if (
                    self.task
                    and str(args[0]) == self.task["task_id"]
                    and str(args[1]) == self.task["tenant_id"]
                )
                else None
            )
        if "FROM irrigation_manual_executions" in sql:
            assert "tenant_id" in sql and "FOR UPDATE" in sql
            return (
                self.execution
                if (
                    self.execution
                    and str(args[0]) == self.execution["execution_id"]
                    and str(args[1]) == self.execution["tenant_id"]
                )
                else None
            )
        if "FROM irrigation_manual_execution_events" in sql:
            assert "tenant_id" in sql
            event = self.events.get(str(args[0]))
            return (
                {"payload": json.dumps(event["payload"])}
                if event and str(args[1]) == event["tenant_id"]
                else None
            )
        raise AssertionError(f"Unexpected fetchrow SQL: {sql}")

    async def fetch(self, sql, *args):
        self.queries.append((sql, args))
        assert "FROM irrigation_manual_execution_events" in sql
        assert "tenant_id" in sql and "task_id" in sql
        # Fake accepts either parameter order; both must be present in the query.
        assert TENANT in map(str, args) and "task-1" in map(str, args)
        return [
            {"payload": json.dumps(e["payload"])}
            for e in self.events.values()
            if e["tenant_id"] == TENANT
            and e["payload"].get("task_id") == "task-1"
            and e["payload"].get("event_type") == "task.irrigation_observation.v1"
        ]

    async def execute(self, sql, *args):
        raise AssertionError(f"Observation endpoint must not UPDATE tasks/ledger/execution: {sql}")


def _harness(monkeypatch, *, role=UserRole.MANAGER):
    conn = ObservationConn()

    @asynccontextmanager
    async def tenant_connection(user):
        yield conn

    async def get_current_user():
        return _user(role)

    # Load the actual permission dependency and router, without importing all
    # unrelated platform routers (which requires scipy and external engines).
    api_dir = Path(__file__).resolve().parents[1] / "api"
    main_tree = ast.parse((api_dir / "main.py").read_text())
    dependency = next(
        node
        for node in main_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "require_permission"
    )
    scope = {
        "Depends": Depends,
        "UserSchema": UserSchema,
        "Permission": Permission,
        "has_permission": has_permission,
        "HTTPException": HTTPException,
        "get_current_user": get_current_user,
    }
    exec(
        compile(ast.Module(body=[dependency], type_ignores=[]), "permission_dependency", "exec"),
        scope,
    )
    stub = types.ModuleType("api.main")
    for name, value in {
        "Permission": Permission,
        "UserSchema": UserSchema,
        "ObservationRequest": ObservationRequest,
        "_OFFLINE_QUEUE": OfflineQueue(),
        "TaskSummary": TaskSummary,
        "TaskListResponse": TaskListResponse,
        "TaskUpdateRequest": TaskUpdateRequest,
        "require_permission": scope["require_permission"],
        "tenant_connection": tenant_connection,
        "_TASK_COLS": "task_id",
        "_TASK_STATUSES": {},
        "_db_unavailable": lambda *args: HTTPException(503, "database unavailable"),
        "_idem_key": lambda: None,
        "get_pool": lambda: None,
        "CommandStore": object,
        "_emit_domain_event": None,
        "_idempotent": None,
        "_row_to_task": None,
    }.items():
        setattr(stub, name, value)
    monkeypatch.setitem(sys.modules, "api.main", stub)
    app = FastAPI()
    for router_name in ("tasks", "observations"):
        name = "task_observation_router_under_test_" + router_name
        spec = importlib.util.spec_from_file_location(
            name, api_dir / "routers" / (router_name + ".py")
        )
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        app.include_router(module.router)
    conn.queue = stub._OFFLINE_QUEUE
    return TestClient(app), conn


def test_observation_records_declared_quantity_without_completing_task(monkeypatch):
    client, conn = _harness(monkeypatch)
    response = client.post(URL, json=_body())
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["event_type"] == "task.irrigation_observation.v1"
    assert payload["task_id"] == "task-1" and payload["actor_id"] == "actor-1"
    assert payload["tenant_id"] == TENANT
    assert payload["computed"]["volume_m3"] == 3000
    assert payload["computed"]["depth_mm"] == 6
    assert payload["computed"]["ledger_eligible"] is False
    assert datetime.fromisoformat(payload["received_at"].replace("Z", "+00:00")).tzinfo is not None
    assert conn.task["status"] == "pending" and conn.execution["state"] == "started"
    assert len(conn.events) == 1


def test_retry_returns_exact_original_payload_and_receipt_time(monkeypatch):
    client, conn = _harness(monkeypatch)
    first = client.post(URL, json=_body())
    again = client.post(URL, json=_body())
    assert first.status_code == again.status_code == 200
    assert again.json() == first.json()
    assert len(conn.events) == 1


def test_same_observation_id_with_changed_payload_conflicts(monkeypatch):
    client, conn = _harness(monkeypatch)
    assert client.post(URL, json=_body()).status_code == 200
    response = client.post(URL, json=_body(volume_m3=3500))
    assert response.status_code == 409
    assert len(conn.events) == 1
    assert next(iter(conn.events.values()))["payload"]["computed"]["volume_m3"] == 3000


@pytest.mark.parametrize("missing", ["task", "execution"])
def test_missing_parent_is_404_and_does_not_append(monkeypatch, missing):
    client, conn = _harness(monkeypatch)
    setattr(conn, missing, None)
    response = client.post(URL, json=_body())
    assert response.status_code == 404
    assert conn.events == {} and conn.writes == []


@pytest.mark.parametrize("parent", ["task", "execution"])
def test_foreign_tenant_parent_is_404_and_does_not_append(monkeypatch, parent):
    client, conn = _harness(monkeypatch)
    getattr(conn, parent)["tenant_id"] = OTHER_TENANT
    response = client.post(URL, json=_body())
    assert response.status_code == 404
    assert conn.events == {} and conn.writes == []


def test_execution_from_another_field_is_rejected(monkeypatch):
    client, conn = _harness(monkeypatch)
    conn.execution["field_id"] = "field-2"
    response = client.post(URL, json=_body())
    assert response.status_code == 422, response.text
    assert conn.events == {} and conn.writes == []


def test_unknown_outcome_stays_null_not_zero(monkeypatch):
    client, conn = _harness(monkeypatch)
    body = _body(outcome="unknown", quantity_method="unknown")
    body["irrigation_observation"].pop("volume_m3")
    body["irrigation_observation"].pop("irrigated_area_ha")
    response = client.post(URL, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["computed"]["volume_m3"] is None
    assert response.json()["computed"]["depth_mm"] is None
    assert response.json()["computed"]["ledger_eligible"] is False


def test_list_reads_evidence_without_mutating_task_or_ledger(monkeypatch):
    client, conn = _harness(monkeypatch)
    saved = client.post(URL, json=_body())
    assert saved.status_code == 200, saved.text
    writes_before = len(conn.writes)
    response = client.get(GET_URL)
    assert response.status_code == 200, response.text
    assert response.json()["irrigation_observations"] == [saved.json()]
    assert response.json()["tasks"] == []
    assert len(conn.writes) == writes_before


def test_list_foreign_task_is_404(monkeypatch):
    client, conn = _harness(monkeypatch)
    conn.task["tenant_id"] = OTHER_TENANT
    assert client.get(GET_URL).status_code == 404
    assert not conn.events


def test_client_cannot_supply_server_identity_or_computed_truth(monkeypatch):
    client, conn = _harness(monkeypatch)
    response = client.post(
        URL, json=_body(tenant_id=OTHER_TENANT, computed={"ledger_eligible": True})
    )
    assert response.status_code == 422
    assert not conn.queries and not conn.events


def test_worker_can_record_observation_without_field_edit_permission(monkeypatch):
    client, conn = _harness(monkeypatch, role=UserRole.WORKER)
    response = client.post(URL, json=_body())
    assert response.status_code == 200, response.text
    assert len(conn.events) == 1


def test_viewer_cannot_record_observation(monkeypatch):
    client, conn = _harness(monkeypatch, role=UserRole.VIEWER)
    response = client.post(URL, json=_body())
    assert response.status_code == 403, response.text
    assert not conn.queries and not conn.events


def test_replay_after_lifecycle_advance_returns_original_observation(monkeypatch):
    client, conn = _harness(monkeypatch)
    first = client.post(URL, json=_body())
    assert first.status_code == 200
    conn.execution["state"] = "stopped"
    replay = client.post(URL, json=_body())
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert conn.execution["state"] == "stopped" and len(conn.events) == 1


def test_foreign_observation_id_collision_never_exposes_payload(monkeypatch):
    client, conn = _harness(monkeypatch)
    conn.events[OBSERVATION] = {
        "tenant_id": OTHER_TENANT,
        "payload": {"private_marker": "foreign-private-value", "actor_id": "other"},
    }
    response = client.post(URL, json=_body())
    assert response.status_code == 409
    assert "foreign-private-value" not in response.text
    assert len(conn.events) == 1


def test_list_excludes_other_task_tenant_and_event_types(monkeypatch):
    client, conn = _harness(monkeypatch)
    saved = client.post(URL, json=_body())
    assert saved.status_code == 200
    for event_id, tenant, changes in (
        ("other-task", TENANT, {"task_id": "task-2"}),
        ("other-tenant", OTHER_TENANT, {}),
        ("other-type", TENANT, {"event_type": "lifecycle.confirmed"}),
    ):
        conn.events[event_id] = {"tenant_id": tenant, "payload": {**saved.json(), **changes}}
    assert client.get(GET_URL).json()["irrigation_observations"] == [saved.json()]


def test_full_platform_registers_and_serves_observation_routes(monkeypatch):
    """Exercise real auto-registration in addition to the isolated router tests."""
    import api.main as main
    from api.routers import observations, tasks

    conn = ObservationConn()

    @asynccontextmanager
    async def tenant_connection(user):
        yield conn

    monkeypatch.setattr(tasks, "tenant_connection", tenant_connection)
    monkeypatch.setattr(observations, "tenant_connection", tenant_connection)
    monkeypatch.setitem(main.app.dependency_overrides, main.get_current_user, _user)
    paths = main.app.openapi()["paths"]
    assert "post" in paths["/api/v1/observations"]
    assert "get" in paths["/api/v1/tasks"]
    assert "/api/v1/tasks/{task_id}/irrigation-observations" not in paths
    client = TestClient(main.app)
    saved = client.post(URL, json=_body())
    assert saved.status_code == 200, saved.text
    read = client.get(GET_URL)
    assert read.status_code == 200, read.text
    assert read.json()["irrigation_observations"] == [saved.json()]


def _legacy_body():
    return {
        "tenant_id": TENANT,
        "field_id": "field-1",
        "observable_id": "soil_moisture",
        "value": 0.25,
        "unit": "m3/m3",
        "measured_at": "2026-01-01T10:00:00Z",
    }


def test_legacy_observation_contract_remains_queued(monkeypatch):
    client, conn = _harness(monkeypatch)
    from api import offline_pending_db

    async def persist(op, user):
        return None

    monkeypatch.setattr(offline_pending_db, "persist_pending_best_effort", persist)
    response = client.post(URL, json=_legacy_body())
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "recorded"
    assert response.json()["queued_for_sync"] is True
    assert len(conn.queue.peek_pending(TENANT)) == 1
    assert not conn.events and not conn.queries


def test_malformed_irrigation_envelope_cannot_fall_back_to_legacy(monkeypatch):
    client, conn = _harness(monkeypatch)
    body = {**_legacy_body(), "task_id": "task-1", "irrigation_observation": {"outcome": "unknown"}}
    response = client.post(URL, json=body)
    assert response.status_code == 422, response.text
    assert not conn.events and not conn.queries and not conn.queue.peek_pending(TENANT)


def test_irrigation_envelope_rejects_unknown_top_level_fields(monkeypatch):
    client, conn = _harness(monkeypatch)
    response = client.post(URL, json={**_body(), "unexpected": True})
    assert response.status_code == 422, response.text
    assert not conn.events and not conn.queries and not conn.queue.peek_pending(TENANT)
