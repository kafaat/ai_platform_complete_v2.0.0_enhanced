"""An inspection approval covers one evidence version (v256); a worker links a task receipt.

Priority 3: the supervisor approved photo 1, then the task update path changed the photo while
the close gate only checked that the last hand-off action was "approve". The gate now also
requires the approved version to be the task's latest evidence, unchanged.

Priority 7 (task part): linking an expense to a task needs the expense-write permission
(activity:execute), not analytics:view, and the cost trace stays behind analytics:view.
The real routes are exercised against PostgreSQL in the delivery proof; these fakes pin the
decisions without a database.
"""

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest
from api.main import get_current_user
from api.routers import scouting
from api.routers import simple_farm_book as book
from api.routers import tasks as mod
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_TASK = UUID("6f1c2d3e-4b5a-4c6d-8e7f-a0b1c2d3e4f5")
_TENANT = "00000000-0000-0000-0000-000000000001"
_P1 = "https://evidence.example/visit/photo-1.jpg"
_P2 = "https://evidence.example/visit/photo-2.jpg"


def _digest(photo, notes):
    # The same canonical form as scouting.evidence_digest, kept local so the gate is measured
    # even on a tree without that helper.
    raw = json.dumps([photo, notes], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _user(role=UserRole.MANAGER, user_id="6"):
    return UserSchema(user_id=user_id, tenant_id=_TENANT, role=role, name_ar="مستخدم")


def _task_row(photo):
    return {
        "task_id": str(_TASK),
        "field_id": "wheat",
        "task_type": "scouting",
        "priority": 2,
        "status": "completed",
        "recommended_date": None,
        "estimated_duration_min": None,
        "estimated_cost_usd": None,
        "assigned_to": "5",
        "notes": "اصفرار",
        "photo_url": photo,
        "completed_at": datetime(2026, 11, 12, tzinfo=UTC),
        "created_at": datetime(2026, 11, 1, tzinfo=UTC),
    }


def _pin_harness(monkeypatch, *, photo_now):
    """A pin inspection task approved on version 1 (photo 1); ``photo_now`` is what it shows."""
    versions = [
        {"version": 1, "photo_url": _P1, "notes": "اصفرار"},
    ]
    if photo_now != _P1:
        versions.append({"version": 2, "photo_url": photo_now, "notes": "اصفرار"})
    for v in versions:
        v["digest"] = _digest(v["photo_url"], v["notes"])
    updates, inserted = [], []

    class FakeConn:
        async def fetchval(self, query, *vals):
            # The pre-v256 gate looked the task up here and read only the last action.
            if "source_scouting_pin_id IS NOT NULL" in query:
                return _TASK
            if "FROM inspection_handoffs" in query:
                return "approve"
            raise AssertionError(query)

        async def fetchrow(self, query, *vals):
            if "source_scouting_pin_id IS NOT NULL" in query:
                if "status IN ('completed','cancelled')" in query:
                    return None  # not a reopen
                return {
                    "task_id": _TASK,
                    "field_id": "wheat",
                    "status": "in_progress",
                    "photo_url": photo_now,
                    "notes": "اصفرار",
                }
            if "FROM inspection_handoffs h" in query:
                return {
                    "action": "approve",
                    "evidence_version": 1,
                    "digest": versions[0]["digest"],
                    "latest": versions[-1]["version"],
                }
            if "FROM inspection_evidence_versions" in query:
                return versions[-1]
            if query.startswith("UPDATE field_tasks"):
                updates.append(vals)
                return _task_row(vals[0] if vals[0] in (_P1, _P2) else photo_now)
            if query.startswith("SELECT status"):
                return {"status": "in_progress"}
            raise AssertionError(query)

        async def execute(self, query, *vals):
            assert query.lstrip().startswith("INSERT INTO inspection_evidence_versions"), query
            inserted.append(vals)
            versions.append(
                {"version": vals[3], "photo_url": vals[4], "notes": vals[5], "digest": vals[6]}
            )

    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield FakeConn()

    async def emit(*args, **kwargs):
        return None

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    monkeypatch.setattr(mod, "_emit_domain_event", emit)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = lambda: _user()
    return TestClient(app), updates, inserted


def test_closing_on_evidence_changed_after_approval_is_refused(monkeypatch):
    client, updates, _ = _pin_harness(monkeypatch, photo_now=_P2)
    closed = client.patch(f"/api/v1/tasks/{_TASK}", json={"status": "completed"})
    assert closed.status_code == 409, closed.text
    assert updates == []


def test_closing_with_a_photo_change_in_the_same_request_is_refused(monkeypatch):
    client, updates, inserted = _pin_harness(monkeypatch, photo_now=_P1)
    closed = client.patch(f"/api/v1/tasks/{_TASK}", json={"status": "completed", "photo_url": _P2})
    assert closed.status_code == 409, closed.text
    assert updates == [] and inserted == []


def test_closing_on_the_approved_version_is_allowed(monkeypatch):
    client, updates, _ = _pin_harness(monkeypatch, photo_now=_P1)
    closed = client.patch(f"/api/v1/tasks/{_TASK}", json={"status": "completed"})
    assert closed.status_code == 200, closed.text
    assert len(updates) == 1


def test_a_photo_change_appends_a_new_version_and_keeps_the_approved_one(monkeypatch):
    client, _, inserted = _pin_harness(monkeypatch, photo_now=_P1)
    changed = client.patch(f"/api/v1/tasks/{_TASK}", json={"photo_url": _P2})
    assert changed.status_code == 200, changed.text
    # Version 1 (the approved photo) already matches what was shown, so only version 2 is new.
    assert [(v[3], v[4]) for v in inserted] == [(2, _P2)]
    assert inserted[0][6] == _digest(_P2, "اصفرار")


def test_evidence_digest_separates_photo_and_notes():
    assert scouting.evidence_digest(_P1, "x") == _digest(_P1, "x")
    assert scouting.evidence_digest("a", "b") != scouting.evidence_digest("ab", None)
    assert scouting.evidence_digest(None, None) != scouting.evidence_digest("", "")


def test_only_the_inspector_submit_carries_evidence():
    with pytest.raises(ValueError):
        scouting.InspectionFinding(
            expected_revision=4, action="approve", reason="ok", photo_url=_P2
        )
    sent = scouting.InspectionFinding(
        expected_revision=4, action="submit", reason="ok", photo_url=_P2
    )
    assert sent.photo_url == _P2


def _book_client(monkeypatch, role):
    linked = []

    class FakeConn:
        async def fetchrow(self, query, *vals):
            if "FROM farm_ledger_entries" in query:
                return {
                    "entry_type": "expense",
                    "reverses_entry_id": None,
                    "field_id": None,
                    "farm_id": "farm-1",
                    "task_id": None,
                }
            if "FROM field_tasks t JOIN fields f" in query:
                return {"field_id": "wheat", "farm_id": "farm-1"}
            raise AssertionError(query)

        async def fetchval(self, query, *vals):
            if "SELECT task_id FROM task_expense_links" in query:
                return linked[-1][2] if linked else None
            return None

        async def execute(self, query, *vals):
            assert "INSERT INTO task_expense_links" in query, query
            linked.append(vals)

    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield FakeConn()

    monkeypatch.setattr(book, "tenant_connection", fake_tenant_connection)
    app = FastAPI()
    app.include_router(book.router)
    app.dependency_overrides[get_current_user] = lambda: _user(role, "5")
    return TestClient(app), linked


def test_worker_links_a_receipt_to_the_task_without_analytics(monkeypatch):
    client, linked = _book_client(monkeypatch, UserRole.WORKER)
    done = client.post("/api/v1/farm-book/entries/fbe_1/task", json={"task_id": str(_TASK)})
    assert done.status_code == 200, done.text
    assert done.json() == {"entry_id": "fbe_1", "task_id": str(_TASK)}
    assert linked and linked[0][4] == "5"
    # The totals stay behind analytics:view.
    assert client.get(f"/api/v1/tasks/{_TASK}/cost-trace").status_code == 403


@pytest.mark.parametrize("role", [UserRole.VIEWER, UserRole.AGRONOMIST])
def test_roles_without_expense_write_cannot_link(monkeypatch, role):
    client, linked = _book_client(monkeypatch, role)
    refused = client.post("/api/v1/farm-book/entries/fbe_1/task", json={"task_id": str(_TASK)})
    assert refused.status_code == 403
    assert linked == []
