"""PATCH /api/v1/tasks/{id} honours Idempotency-Key.

The mobile offline outbox replays a task update after a lost reply. Without the key
check every replay ran the UPDATE again and emitted another TASK_UPDATED event.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from api.main import get_current_user
from api.routers import tasks as mod
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPLAY_ID = "0b0c9f6e-1d2a-4e3b-8c4d-5e6f7a8b9c0d"


def _user():
    return UserSchema(
        user_id="u1",
        tenant_id="00000000-0000-0000-0000-000000000001",
        role=UserRole.MANAGER,
        name_ar="مدير",
    )


def _harness(monkeypatch, *, row_exists=True, current_status=None, queries=None):
    updates = []
    events = []
    commands = {}

    class FakeConn:
        # The task under test is not a pin-sourced inspection: the v254 inspection
        # lookups (close gate, reopen event) find no row.
        async def fetchval(self, query, *vals):
            assert "source_scouting_pin_id IS NOT NULL" in query, query
            return None

        async def fetchrow(self, query, *vals):
            if "source_scouting_pin_id IS NOT NULL" in query:
                return None
            if queries is not None:
                queries.append((query, vals))
            if query.startswith("SELECT status"):  # 409/404 disambiguation after a refused guard
                return {"status": current_status} if row_exists else None
            updates.append(vals)
            if not row_exists:
                return None
            # The atomic transition guard binds the allowed source states as the last array.
            allowed = next((v for v in reversed(vals) if isinstance(v, list)), None)
            if current_status is not None and allowed is not None and current_status not in allowed:
                return None
            return {
                "task_id": "t-1",
                "field_id": "field-a",
                "task_type": "irrigation",
                "priority": 2,
                "status": vals[0],
                "recommended_date": None,
                "estimated_duration_min": None,
                "estimated_cost_usd": None,
                "assigned_to": None,
                "notes": None,
                "photo_url": None,
                "completed_at": datetime(2026, 10, 26, tzinfo=UTC),
                "created_at": datetime(2026, 10, 1, tzinfo=UTC),
            }

    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield FakeConn()

    async def emit(conn, user, event_type, *args, **kwargs):
        events.append(event_type)

    class FakeCommandStore:
        def __init__(self, pool, conn=None):
            pass

        async def insert(self, cmd):
            if cmd.command_id in commands:
                return False
            commands[cmd.command_id] = cmd
            return True

        async def get(self, command_id):
            return commands.get(command_id)

        async def mark_succeeded(self, command_id, result):
            from api.command_store import CommandStatus

            commands[command_id].status = CommandStatus.SUCCEEDED
            commands[command_id].result = result

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    monkeypatch.setattr(mod, "_emit_domain_event", emit)
    # raising=False: على كودٍ لا يستورد الاسمين يُقاس السلوك (تنفيذٌ مكرَّر) لا خطأ التجهيز.
    monkeypatch.setattr(mod, "CommandStore", FakeCommandStore, raising=False)
    monkeypatch.setattr(mod, "get_pool", lambda: None, raising=False)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app), updates, events


def test_replayed_update_with_the_same_key_runs_once(monkeypatch):
    c, updates, events = _harness(monkeypatch)
    body = {"status": "completed"}
    first = c.patch("/api/v1/tasks/t-1", json=body, headers={"Idempotency-Key": _REPLAY_ID})
    again = c.patch("/api/v1/tasks/t-1", json=body, headers={"Idempotency-Key": _REPLAY_ID})
    assert first.status_code == 200 and again.status_code == 200
    assert again.json() == first.json()
    assert len(updates) == 1
    assert events == ["TASK_UPDATED"]


def test_same_key_with_a_different_update_is_rejected(monkeypatch):
    c, updates, events = _harness(monkeypatch)
    c.patch(
        "/api/v1/tasks/t-1", json={"status": "completed"}, headers={"Idempotency-Key": _REPLAY_ID}
    )
    resp = c.patch(
        "/api/v1/tasks/t-1", json={"status": "in_progress"}, headers={"Idempotency-Key": _REPLAY_ID}
    )
    assert resp.status_code == 409
    assert len(updates) == 1


def test_without_a_key_each_update_runs(monkeypatch):
    c, updates, events = _harness(monkeypatch)
    c.patch("/api/v1/tasks/t-1", json={"status": "completed"})
    c.patch("/api/v1/tasks/t-1", json={"status": "completed"})
    assert len(updates) == 2
    assert events == ["TASK_UPDATED", "TASK_UPDATED"]


def test_missing_task_is_404_and_records_no_command(monkeypatch):
    c, updates, events = _harness(monkeypatch, row_exists=False)
    resp = c.patch(
        "/api/v1/tasks/t-1", json={"status": "completed"}, headers={"Idempotency-Key": _REPLAY_ID}
    )
    assert resp.status_code == 404
    assert events == []


def test_illegal_transition_is_409_and_emits_nothing(monkeypatch):
    c, updates, events = _harness(monkeypatch, current_status="completed")
    resp = c.patch("/api/v1/tasks/t-1", json={"status": "cancelled"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == {
        "error": "illegal_task_transition",
        "from": "completed",
        "to": "cancelled",
    }
    assert events == []


def test_cancelled_task_cannot_be_completed(monkeypatch):
    c, _, events = _harness(monkeypatch, current_status="cancelled")
    assert c.patch("/api/v1/tasks/t-1", json={"status": "completed"}).status_code == 409
    assert events == []


def test_client_completed_at_is_stored_instead_of_server_now(monkeypatch):
    queries = []
    c, _, events = _harness(monkeypatch, current_status="in_progress", queries=queries)
    resp = c.patch(
        "/api/v1/tasks/t-1",
        json={
            "status": "completed",
            "completed_at": "2026-10-20T06:30:00Z",
            "actual_cost_usd": 12.5,
        },
    )
    assert resp.status_code == 200 and events == ["TASK_UPDATED"]
    sql, vals = queries[-1]
    assert "NOW()" not in sql.split("updated_at")[0]  # the completion stamp is the client's
    assert datetime(2026, 10, 20, 6, 30, tzinfo=UTC) in vals and 12.5 in vals
    assert "actual_cost_usd = $" in sql and "= ANY(" in sql


def test_server_stamp_is_kept_on_repeat_completion_and_cleared_on_reopen(monkeypatch):
    queries = []
    c, _, _ = _harness(monkeypatch, current_status="completed", queries=queries)
    assert c.patch("/api/v1/tasks/t-1", json={"status": "completed"}).status_code == 200
    assert "THEN completed_at ELSE NOW()" in queries[-1][0]
    assert c.patch("/api/v1/tasks/t-1", json={"status": "pending"}).status_code == 200
    assert "completed_at = NULL" in queries[-1][0]


def test_future_completed_at_is_rejected_before_any_update(monkeypatch):
    c, updates, _ = _harness(monkeypatch, current_status="pending")
    resp = c.patch(
        "/api/v1/tasks/t-1", json={"status": "completed", "completed_at": "2999-01-01T00:00:00Z"}
    )
    assert resp.status_code == 422 and updates == []


def test_idempotency_digest_of_a_legacy_body_is_unchanged(monkeypatch):
    """New optional fields are excluded from the digest when absent, so an outbox replay of a
    request recorded before this change still matches its stored command."""
    import hashlib
    import json

    seen = {}

    class Store:
        def __init__(self, pool, conn=None):
            pass

    async def fake_idempotent(store, key, work, **kw):
        seen["digest"] = kw["request_digest"]
        return await work()

    c, _, _ = _harness(monkeypatch, current_status="pending")
    monkeypatch.setattr(mod, "_idempotent", fake_idempotent)
    monkeypatch.setattr(mod, "CommandStore", Store)
    c.patch(
        "/api/v1/tasks/t-1", json={"status": "in_progress"}, headers={"Idempotency-Key": _REPLAY_ID}
    )
    legacy = {"task_id": "t-1", "status": "in_progress", "photo_url": None, "notes": None}
    expected = hashlib.sha256(
        json.dumps(legacy, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert seen["digest"] == expected
