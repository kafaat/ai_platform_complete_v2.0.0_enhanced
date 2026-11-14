"""Notification delivery receipts follow their state machine on a migrated PostgreSQL.

``POST /api/v1/notifications/delivery`` upserts one row per (tenant, alert_key, channel) in
``notification_delivery`` (v83, RLS + FORCE). The transition rule lives in the
``ON CONFLICT … DO UPDATE … WHERE`` clause, so PostgreSQL decides it under the row lock, not a
read-then-write in Python. The unit test next to the router emulates that SQL; this module runs
the real statement:

- every (current, requested) pair: written, idempotent replay (no write, ``updated_at``
  unchanged, no event) or 409 (nothing changed);
- one ``NOTIFICATION_DELIVERED`` event per written transition, none for a replay;
- a receipt for the same alert key in another tenant never touches this tenant's row;
- a late ``sent`` racing a ``delivered`` never leaves the row behind ``delivered``.

The handler runs under a throwaway NOBYPASSRLS role created from the superuser DSN of the
shared Integration step. That step sets ``NOTIFICATION_DELIVERY_CERTIFICATION_REQUIRED=1``, so a
missing or unmigrated database fails the module instead of turning it into a green skip.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

asyncpg = pytest.importorskip("asyncpg")
pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
STATUSES = ("queued", "sent", "failed", "delivered")
ALLOWED = {
    "queued": {"sent", "failed", "delivered"},
    "sent": {"failed", "delivered"},
    "failed": {"sent", "delivered"},
    "delivered": set(),
}


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        if await conn.fetchval("SELECT to_regclass('public.notification_delivery')") is None:
            return "schema not migrated (notification_delivery missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
_REQUIRED = os.getenv("NOTIFICATION_DELIVERY_CERTIFICATION_REQUIRED") == "1"


@pytest.fixture(autouse=True)
def _database_or_declared_skip():
    if _WHY:
        message = f"notification-delivery live certification has no database: {_WHY}"
        if _REQUIRED:
            pytest.fail(message, pytrace=False)
        pytest.skip(f"declared skip (not a pass): {message}")


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api.routers import notifications

    return main, notifications


def _user(tenant: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id=f"u-{tenant[:8]}", tenant_id=tenant, role=UserRole.MANAGER, name_ar="مدير"
    )


class Live:
    """Owner connection for setup/measurement + a pool that runs as a NOBYPASSRLS role."""

    def __init__(self):
        self.tenant_a = str(uuid.uuid4())
        self.tenant_b = str(uuid.uuid4())
        self.role = f"nd_rls_{uuid.uuid4().hex[:10]}"

    async def __aenter__(self):
        self.owner = await asyncpg.connect(DSN)
        await self.owner.execute(
            f'CREATE ROLE "{self.role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{self.role}";'
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{self.role}";'
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{self.role}";'
        )
        role = self.role

        async def setup(conn):
            await conn.execute(f'SET ROLE "{role}"')

        self.pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4, setup=setup)
        return self

    async def seed(self, tenant: str, key: str, status: str, error: str | None = None):
        await self.owner.execute(
            "INSERT INTO notification_delivery (tenant_id, alert_key, channel, status, error, "
            "updated_at) VALUES ($1::uuid, $2, 'push', $3, $4, NOW() - INTERVAL '1 hour')",
            tenant,
            key,
            status,
            error,
        )

    async def row(self, tenant: str, key: str):
        return await self.owner.fetchrow(
            "SELECT delivery_id, status, error, updated_at FROM notification_delivery "
            "WHERE tenant_id = $1::uuid AND alert_key = $2 AND channel = 'push'",
            tenant,
            key,
        )

    async def events(self, delivery_id) -> list[str]:
        rows = await self.owner.fetch(
            "SELECT payload->>'status' AS status FROM events "
            "WHERE entity_type = 'notification_delivery' AND entity_id = $1 ORDER BY seq",
            str(delivery_id),
        )
        return [r["status"] for r in rows]

    async def __aexit__(self, *exc):
        try:
            for tenant in (self.tenant_a, self.tenant_b):
                await self.owner.execute(
                    "DELETE FROM notification_delivery WHERE tenant_id = $1::uuid", tenant
                )
                await self.owner.execute("SET session_replication_role = replica")
                await self.owner.execute(
                    "DELETE FROM events WHERE tenant_id::text = $1 "
                    "AND entity_type = 'notification_delivery'",
                    tenant,
                )
                await self.owner.execute("SET session_replication_role = origin")
        finally:
            await self.pool.close()
            await self.owner.execute(f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"')
            await self.owner.close()


def _run(coro_fn, monkeypatch):
    main, notifications = _platform()

    async def body():
        async with Live() as live:
            monkeypatch.setattr(main, "_DB_POOL", live.pool)
            await coro_fn(live, notifications)

    asyncio.run(body())


async def _post(notifications, tenant: str, key: str, status: str, error: str | None = None):
    receipt = notifications.DeliveryReceipt(
        alert_key=key, channel="push", status=status, error=error
    )
    return await notifications.upsert_notification_delivery(receipt, user=_user(tenant))


def _error_for(status: str) -> str | None:
    return "timeout" if status == "failed" else None


# ── the full transition matrix, decided by PostgreSQL ─────────────────────────


def test_every_transition_is_written_replayed_or_refused(monkeypatch):
    from fastapi import HTTPException

    async def case(live, notifications):
        outcomes = {}
        for current in STATUSES:
            for wanted in STATUSES:
                key = f"field:{current}:{wanted}"
                await live.seed(live.tenant_a, key, current, _error_for(current))
                before = await live.row(live.tenant_a, key)
                try:
                    await _post(notifications, live.tenant_a, key, wanted, _error_for(wanted))
                    answered = 200
                except HTTPException as exc:
                    answered = exc.status_code
                after = await live.row(live.tenant_a, key)
                events = await live.events(after["delivery_id"])
                if wanted in ALLOWED[current]:
                    expected = ("written", 200, wanted, [wanted])
                    got = (
                        "written" if after["updated_at"] > before["updated_at"] else "unchanged",
                        answered,
                        after["status"],
                        events,
                    )
                elif wanted == current:
                    expected = ("replay", 200, current, [])
                    got = (
                        "replay" if after["updated_at"] == before["updated_at"] else "rewritten",
                        answered,
                        after["status"],
                        events,
                    )
                else:
                    expected = ("refused", 409, current, [])
                    got = (
                        "refused" if after["updated_at"] == before["updated_at"] else "rewritten",
                        answered,
                        after["status"],
                        events,
                    )
                outcomes[(current, wanted)] = (got, expected)
        wrong = {pair: v for pair, v in outcomes.items() if v[0] != v[1]}
        assert not wrong, f"(got, expected) per transition: {wrong}"

    _run(case, monkeypatch)


def test_a_new_failure_reason_is_written_and_its_replay_is_not(monkeypatch):
    async def case(live, notifications):
        key = "field:retry:reason"
        await _post(notifications, live.tenant_a, key, "failed", "offline")
        await _post(notifications, live.tenant_a, key, "failed", "timeout")
        first = await live.row(live.tenant_a, key)
        await _post(notifications, live.tenant_a, key, "failed", "timeout")
        second = await live.row(live.tenant_a, key)
        assert first["error"] == "timeout" and second["updated_at"] == first["updated_at"]
        assert await live.events(first["delivery_id"]) == ["failed", "failed"]

    _run(case, monkeypatch)


# ── tenant isolation and a late callback racing the terminal one ─────────────


def test_the_same_alert_key_in_another_tenant_is_its_own_row(monkeypatch):
    async def case(live, notifications):
        key = "field:shared:key"
        await _post(notifications, live.tenant_a, key, "delivered")
        out_b = await _post(notifications, live.tenant_b, key, "queued")
        row_a = await live.row(live.tenant_a, key)
        row_b = await live.row(live.tenant_b, key)
        assert row_a["status"] == "delivered" and row_b["status"] == "queued"
        assert str(row_a["delivery_id"]) != out_b.delivery_id

    _run(case, monkeypatch)


def test_a_late_sent_racing_delivered_never_leaves_the_row_behind(monkeypatch):
    from fastapi import HTTPException

    async def case(live, notifications):
        finals = []
        for i in range(10):
            key = f"field:race:{i}"
            await live.seed(live.tenant_a, key, "queued")
            results = await asyncio.gather(
                _post(notifications, live.tenant_a, key, "delivered"),
                _post(notifications, live.tenant_a, key, "sent"),
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    assert isinstance(r, HTTPException) and r.status_code == 409, r
            row = await live.row(live.tenant_a, key)
            finals.append(row["status"])
            assert (await live.events(row["delivery_id"]))[-1] == "delivered"
        assert set(finals) == {"delivered"}

    _run(case, monkeypatch)


def test_a_repeated_status_after_a_round_trip_is_still_its_own_event(monkeypatch):
    """emit_event dedups on the payload per day; the row version keeps real writes apart."""

    async def case(live, notifications):
        key = "field:round:trip"
        await _post(notifications, live.tenant_a, key, "failed", "timeout")
        await _post(notifications, live.tenant_a, key, "sent")
        await _post(notifications, live.tenant_a, key, "failed", "timeout")
        row = await live.row(live.tenant_a, key)
        assert await live.events(row["delivery_id"]) == ["failed", "sent", "failed"]

    _run(case, monkeypatch)
