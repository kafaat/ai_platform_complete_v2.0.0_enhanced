"""The unified-timeline facade maps errors honestly: a tenant refusal is 404, a DB fault is degraded.

The live proof is tests_v9/test_field_timeline_tenant_scope_live_pg.py (real handler, a migrated
PostgreSQL, a NOBYPASSRLS role). This pins the two branches at unit level, where coverage is
collected: the HTTPException raised by the tenant check propagates instead of becoming
``200 degraded``, and any other read failure answers ``degraded`` without echoing its text.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from api.routers import field_workspace_timeline as timeline
from fastapi import HTTPException

pytestmark = pytest.mark.unit


class _User:
    tenant_id = "00000000-0000-0000-0000-000000000001"


def _call():
    return asyncio.run(
        timeline.field_unified_timeline_facade(
            "f-1", limit=50, newest_first=True, category=None, season_id=None, user=_User()
        )
    )


@pytest.fixture
def wired(monkeypatch):
    class _Conn:
        error: Exception | None = None

        async def fetch(self, *_args):
            if self.error is not None:
                raise self.error
            return []

    conn = _Conn()

    @asynccontextmanager
    async def tenant_connection(_user):
        yield conn

    monkeypatch.setattr(timeline.api_main, "_DB_POOL", object())
    monkeypatch.setattr(timeline, "tenant_connection", tenant_connection)
    return conn


def test_a_field_outside_the_tenant_is_a_404_not_a_degraded_200(wired, monkeypatch):
    async def refuse(_conn, _field_id):
        raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")

    monkeypatch.setattr(timeline, "_assert_field_in_tenant", refuse)
    with pytest.raises(HTTPException) as caught:
        _call()
    assert caught.value.status_code == 404


def test_a_read_failure_is_degraded_and_does_not_echo_the_database_error(wired, monkeypatch):
    async def allow(_conn, _field_id):
        return None

    monkeypatch.setattr(timeline, "_assert_field_in_tenant", allow)
    wired.error = RuntimeError('relation "events" does not exist (internal detail)')
    out = _call()
    assert out["degraded"] is True and out["events"] == []
    assert "internal detail" not in str(out) and "events" not in out["error"]
