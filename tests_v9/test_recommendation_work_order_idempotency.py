"""Actual CommandStore/helper replay and rollback using a transactional DB double."""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit


class Connection:
    def __init__(self):
        self.commands = {}
        self.orders = []
        self.fields = {"field-1"}
        self.locked = False
        self.fail = False

    async def fetchval(self, sql, field_id):
        return field_id in self.fields

    async def fetchrow(self, sql, *args):
        if "FROM commands" in sql:
            assert self.locked
            return self.commands.get(str(args[0]))
        assert "INSERT INTO work_orders" in sql and self.locked
        if self.fail:
            raise RuntimeError("database outage")
        self.orders.append(args)
        return {"work_order_id": f"wo-{len(self.orders)}"}

    async def execute(self, sql, *args):
        if "pg_advisory_xact_lock" in sql:
            self.locked = True
            return "SELECT 1"
        assert self.locked
        key = str(args[0])
        if "INSERT INTO commands" in sql:
            if key in self.commands:
                return "INSERT 0 0"
            self.commands[key] = dict(
                command_id=key,
                command_type=args[1],
                actor_id=args[2],
                tenant_id=args[3],
                payload=args[4],
                source=args[5],
                status="pending",
                result=None,
                error=None,
                retry_count=0,
                created_at=datetime.now(UTC),
            )
            return "INSERT 0 1"
        assert "UPDATE commands" in sql
        self.commands[key].update(status="succeeded", result=args[1])
        return "UPDATE 1"


@pytest.fixture
def runtime(monkeypatch):
    import api.main  # noqa: F401 — initializes the registered router graph
    from api.routers import agro_intelligence as module

    conn = Connection()

    @asynccontextmanager
    async def transaction(user):
        snapshot = deepcopy((conn.commands, conn.orders))
        try:
            yield conn
        except Exception:
            conn.commands, conn.orders = snapshot
            raise
        finally:
            conn.locked = False

    monkeypatch.setattr(module, "tenant_connection", transaction)
    monkeypatch.setattr(module, "get_pool", lambda: None)
    monkeypatch.setattr(module, "_emit_domain_event", AsyncMock())
    user = SimpleNamespace(user_id="user-1", tenant_id="00000000-0000-0000-0000-000000000007")
    work = {
        "field_id": "field-1",
        "wo_type": "scouting",
        "status": "planned",
        "payload": {"recommendation": "rec-1"},
    }
    return module, conn, user, work


@pytest.mark.asyncio
async def test_retry_returns_same_order_and_emits_one_event(runtime):
    module, conn, user, work = runtime
    first = await module._persist_work_order(user, work, "stable-key")
    second = await module._persist_work_order(user, work, "stable-key")
    assert first == second == "wo-1"
    assert len(conn.orders) == len(conn.commands) == 1
    module._emit_domain_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_payload_mutation_is_conflict(runtime):
    module, conn, user, work = runtime
    await module._persist_work_order(user, work, "stable-key")
    with pytest.raises(HTTPException) as error:
        await module._persist_work_order(user, work | {"wo_type": "spraying"}, "stable-key")
    assert error.value.status_code == 409 and len(conn.orders) == 1


@pytest.mark.asyncio
async def test_failed_insert_rolls_back_command_and_retry_can_create(runtime):
    module, conn, user, work = runtime
    conn.fail = True
    assert await module._persist_work_order(user, work, "stable-key") is None
    assert conn.commands == {} and conn.orders == []
    conn.fail = False
    assert await module._persist_work_order(user, work, "stable-key") == "wo-1"


@pytest.mark.asyncio
async def test_field_outside_tenant_cannot_create(runtime):
    module, conn, user, work = runtime
    with pytest.raises(HTTPException) as error:
        await module._persist_work_order(user, work | {"field_id": "other-field"}, "stable-key")
    assert error.value.status_code == 404
    assert conn.orders == [] and conn.commands == {}
