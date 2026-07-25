from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import UUID

SERVICE = Path(__file__).resolve().parents[2] / "services" / "sahool-platform"
if str(SERVICE) not in sys.path:
    sys.path.insert(0, str(SERVICE))

from api import irrigation_reservation_lifecycle_worker as worker  # noqa: E402

TENANT = UUID("11111111-1111-1111-1111-111111111111")


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _Conn:
    def __init__(self):
        self.executed = []

    async def fetch(self, _sql):
        return [{"tenant_id": TENANT}]

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    def transaction(self):
        return _Tx()


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


def test_sweep_scopes_tenant_and_uses_governed_expiry(monkeypatch):
    conn = _Conn()
    seen = []

    async def fake_expire(_conn, *, tenant_id):
        seen.append(tenant_id)
        return 2

    monkeypatch.setattr(worker, "expire_due", fake_expire)
    total = asyncio.run(worker.expire_all_tenants(_Pool(conn)))
    assert total == 2
    assert seen == [TENANT]
    assert any("app.current_tenant" in sql for sql, _ in conn.executed)


def test_poll_interval_is_fail_safe(monkeypatch):
    monkeypatch.setenv("IRRIGATION_RESERVATION_LIFECYCLE_POLL_SECONDS", "bad")
    assert worker.poll_seconds() == 15.0
    monkeypatch.setenv("IRRIGATION_RESERVATION_LIFECYCLE_POLL_SECONDS", "0")
    assert worker.poll_seconds() == 1.0
