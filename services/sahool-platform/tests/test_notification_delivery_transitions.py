"""Notification delivery route contract: atomic SQL, replay and event semantics.

This is a unit test with an emulated DB state machine, not a replacement for a
PostgreSQL integration/RLS test. Uses the real route handler and model.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import api.main  # noqa: F401 — initialize existing app imports
import pytest
from api.routers import notifications as mod
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_ALLOWED = {
    "queued": {"queued", "sent", "failed", "delivered"},
    "sent": {"sent", "failed", "delivered"},
    "failed": {"failed", "sent", "delivered"},
    "delivered": {"delivered"},
}


class FakeConnection:
    def __init__(self):
        self.rows = {}
        self.writes = 0
        self.seen_sql = []

    async def fetchrow(self, statement, *params):
        self.seen_sql.append(statement)
        tenant_id, alert_key, channel = params[:3]
        key = (tenant_id, alert_key, channel)
        existing = self.rows.get(key)
        if statement.lstrip().startswith("INSERT INTO notification_delivery"):
            assert "ON CONFLICT (tenant_id, alert_key, channel)" in statement
            assert "notification_delivery.status = 'delivered'" not in statement
            assert "notification_delivery.error IS DISTINCT FROM EXCLUDED.error" in statement
            wanted, error = params[3:5]
            if existing is not None:
                old_status = existing["status"]
                if wanted not in _ALLOWED[old_status]:
                    return None
                if wanted == old_status and error == existing["error"]:
                    return None  # ON CONFLICT WHERE false; no write or event
            self.writes += 1
            row = {
                "delivery_id": f"d-{len(self.rows) + 1}"
                if existing is None
                else existing["delivery_id"],
                "alert_key": alert_key,
                "channel": channel,
                "status": wanted,
                "error": error,
                "updated_at": datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=self.writes),
            }
            self.rows[key] = row
            return dict(row)
        if statement.lstrip().startswith("SELECT delivery_id"):
            return None if existing is None else dict(existing)
        raise AssertionError("Unexpected SQL")


def _run(handler, status, tenant="tenant1", error=None):
    return asyncio.run(
        handler(
            mod.DeliveryReceipt(alert_key="alert", channel="push", status=status, error=error),
            SimpleNamespace(tenant_id=tenant),
        )
    )


def _harness(monkeypatch):
    conn = FakeConnection()
    sent_events = []

    @asynccontextmanager
    async def tenant_connection(user):
        yield conn

    async def record_event(conn, user, name, kind, id, payload):
        sent_events.append((name, payload["status"]))

    monkeypatch.setattr(mod, "tenant_connection", tenant_connection)
    monkeypatch.setattr(mod, "_emit_domain_event", record_event)
    return conn, sent_events


def test_queued_sent_delivered_and_replay(monkeypatch):
    conn, events = _harness(monkeypatch)
    assert _run(mod.upsert_notification_delivery, "queued").status == "queued"
    assert _run(mod.upsert_notification_delivery, "sent").status == "sent"
    delivered = _run(mod.upsert_notification_delivery, "delivered")
    assert delivered.status == "delivered"
    assert _run(mod.upsert_notification_delivery, "delivered").delivery_id == delivered.delivery_id
    assert conn.writes == 3
    # One event per written transition; the delivered replay publishes nothing.
    assert events == [
        ("NOTIFICATION_DELIVERED", "queued"),
        ("NOTIFICATION_DELIVERED", "sent"),
        ("NOTIFICATION_DELIVERED", "delivered"),
    ]


@pytest.mark.parametrize("late", ("queued", "sent", "failed"))
def test_terminal_delivery_rejects_late_callbacks(monkeypatch, late):
    conn, events = _harness(monkeypatch)
    _run(mod.upsert_notification_delivery, "delivered")
    with pytest.raises(HTTPException) as exc:
        _run(mod.upsert_notification_delivery, late, error="failure" if late == "failed" else None)
    assert exc.value.status_code == 409
    assert conn.writes == 1
    assert events == [("NOTIFICATION_DELIVERED", "delivered")]


def test_retry_after_failed_does_not_requeue(monkeypatch):
    conn, events = _harness(monkeypatch)
    _run(mod.upsert_notification_delivery, "failed", error="timeout")
    with pytest.raises(HTTPException) as exc:
        _run(mod.upsert_notification_delivery, "queued")
    assert exc.value.status_code == 409
    assert _run(mod.upsert_notification_delivery, "sent").status == "sent"
    assert _run(mod.upsert_notification_delivery, "delivered").status == "delivered"
    # The refused requeue publishes nothing; the failure itself is an audited transition.
    assert events == [
        ("NOTIFICATION_DELIVERED", "failed"),
        ("NOTIFICATION_DELIVERED", "sent"),
        ("NOTIFICATION_DELIVERED", "delivered"),
    ]


def test_a_changed_failure_reason_is_one_event_and_its_replay_none(monkeypatch):
    conn, events = _harness(monkeypatch)
    _run(mod.upsert_notification_delivery, "failed", error="offline")
    _run(mod.upsert_notification_delivery, "failed", error="timeout")
    _run(mod.upsert_notification_delivery, "failed", error="timeout")
    assert conn.writes == 2
    assert events == [("NOTIFICATION_DELIVERED", "failed"), ("NOTIFICATION_DELIVERED", "failed")]


def test_success_with_error_is_rejected_before_db(monkeypatch):
    conn, _ = _harness(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        _run(mod.upsert_notification_delivery, "delivered", error="bad")
    assert exc.value.status_code == 422 and conn.writes == 0


def test_unknown_status_is_rejected_before_db(monkeypatch):
    conn, _ = _harness(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        _run(mod.upsert_notification_delivery, "unknown")
    assert exc.value.status_code == 422 and conn.writes == 0


def test_tenant_key_prevents_replaying_other_tenant_receipt(monkeypatch):
    conn, events = _harness(monkeypatch)
    _run(mod.upsert_notification_delivery, "delivered", tenant="tenant1")
    _run(mod.upsert_notification_delivery, "queued", tenant="tenant2")
    assert conn.writes == 2
    assert conn.rows[("tenant1", "alert", "push")]["status"] == "delivered"
    assert conn.rows[("tenant2", "alert", "push")]["status"] == "queued"
    assert len(events) == 2
