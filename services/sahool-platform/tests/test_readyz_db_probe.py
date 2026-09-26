"""MED-001 (شهادة P12): readyz يجب أن يفحص اعتماديّة القاعدة فعليّاً، لا النواة فقط.

كان readyz يستند إلى handle_readyz (فحص in-memory) فيُرجِع ready رغم سقوط Postgres
(إيجابيّة كاذبة توجّه المنظّم حركةً لنسخة معطوبة). db_probe_ok يُجري SELECT 1 فعليّاً.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from core.api_adapter import db_probe_ok

pytestmark = pytest.mark.unit


class _Conn:
    def __init__(self, fail: bool):
        self._fail = fail

    async def fetchval(self, _q):
        if self._fail:
            raise RuntimeError("connection refused")
        return 1


class _Acquire:
    def __init__(self, fail: bool):
        self._fail = fail

    async def __aenter__(self):
        return _Conn(self._fail)

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, fail: bool):
        self._fail = fail

    def acquire(self, *, timeout):
        assert timeout > 0
        return _Acquire(self._fail)


@pytest.mark.asyncio
async def test_db_down_is_not_ready():
    """مسبح قائم لكن الفحص يفشل (Postgres ساقط) ⇒ ليست جاهزة (لا إيجابيّة كاذبة)."""
    assert await db_probe_ok(_Pool(fail=True)) is False


@pytest.mark.asyncio
async def test_db_up_is_ready():
    assert await db_probe_ok(_Pool(fail=False)) is True


@pytest.mark.asyncio
async def test_missing_pool_is_not_ready_by_default(monkeypatch):
    monkeypatch.delenv("SAHOOL_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert await db_probe_ok(None) is False


@pytest.mark.parametrize("environment", ["development", "local", "test", "staging", "production"])
async def test_configured_database_without_pool_is_not_ready(monkeypatch, environment):
    monkeypatch.setenv("SAHOOL_ENV", environment)
    monkeypatch.setenv("DATABASE_URL", "postgresql://sahool_app:invalid@localhost/sahool")
    assert await db_probe_ok(None) is False


@pytest.mark.parametrize("environment", ["staging", "production", "unknown"])
async def test_deployed_environment_requires_database(monkeypatch, environment):
    monkeypatch.setenv("SAHOOL_ENV", environment)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert await db_probe_ok(None) is False


@pytest.mark.parametrize("environment", ["development", "local", "test"])
async def test_explicit_local_database_free_mode(monkeypatch, environment):
    monkeypatch.setenv("SAHOOL_ENV", environment)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    assert await db_probe_ok(None) is True


async def test_railway_cannot_use_local_database_free_mode(monkeypatch):
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "staging-environment")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert await db_probe_ok(None) is False


@pytest.mark.parametrize("blocked_at", ["acquire", "query"])
async def test_probe_has_a_deadline(blocked_at):
    released = []

    class BlockedConnection:
        async def fetchval(self, query):
            assert query == "SELECT 1"
            await asyncio.Event().wait()

    class BlockedPool:
        @asynccontextmanager
        async def acquire(self, *, timeout):
            assert timeout == 0.02
            try:
                if blocked_at == "acquire":
                    await asyncio.Event().wait()
                yield BlockedConnection()
            finally:
                released.append(True)

    assert (
        await asyncio.wait_for(db_probe_ok(BlockedPool(), timeout_seconds=0.02), timeout=1) is False
    )
    assert released == [True]


async def test_probe_does_not_disclose_exception_or_credentials(capsys, caplog):
    class SecretConnection:
        async def fetchval(self, query):
            raise RuntimeError("postgresql://sahool_app:DO_NOT_PRINT@localhost/sahool")

    class SecretPool:
        @asynccontextmanager
        async def acquire(self, *, timeout):
            assert timeout > 0
            yield SecretConnection()

    assert await db_probe_ok(SecretPool()) is False
    captured = capsys.readouterr()
    assert "DO_NOT_PRINT" not in captured.out + captured.err + caplog.text


@pytest.mark.parametrize(
    ("pool", "environment", "dsn", "status", "db"),
    [
        (None, "staging", "postgresql://unused/sahool", 503, "down"),
        (None, "staging", "", 503, "down"),
        (_Pool(fail=True), "staging", "postgresql://unused/sahool", 503, "down"),
        (_Pool(fail=False), "staging", "postgresql://unused/sahool", 200, "up"),
        (None, "development", "", 200, "disabled"),
    ],
)
def test_readyz_http_contract(monkeypatch, pool, environment, dsn, status, db):
    from api import main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SAHOOL_ENV", environment)
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    monkeypatch.setattr(main, "_DB_POOL", pool)
    # No context manager: do not start background jobs or real DB connections.
    client = TestClient(main.app)
    response = client.get("/readyz")
    assert response.status_code == status
    assert response.json()["db"] == db
    assert client.get("/healthz").status_code == 200


async def test_startup_authentication_failure_cannot_report_ready(monkeypatch):
    from unittest.mock import AsyncMock

    import asyncpg
    from api import main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATABASE_URL", "postgresql://sahool_app:invalid@localhost/sahool")
    monkeypatch.setenv("SAHOOL_ENV", "staging")
    monkeypatch.setattr(main, "_DB_POOL", None)
    create_pool = AsyncMock(side_effect=asyncpg.InvalidPasswordError("authentication failed"))
    monkeypatch.setattr(asyncpg, "create_pool", create_pool)
    await main._init_db_pool()
    create_pool.assert_awaited_once()
    response = TestClient(main.app).get("/readyz")
    assert response.status_code == 503
    assert response.json()["db"] == "down"


def test_readyz_endpoint_awaits_db_probe():
    """حارس ثابت: نقطة readyz في المنصّة تستدعي db_probe_ok (لا فحص نواة فقط)."""
    import os

    base = os.path.join(os.path.dirname(__file__), "..", "api", "main.py")
    health = os.path.join(os.path.dirname(__file__), "..", "api", "routers", "platform_health.py")
    # P2: نقطة readyz انتقلت إلى routers/platform_health.py — نفحص الملفّين
    src = open(base, encoding="utf-8").read() + open(health, encoding="utf-8").read()
    assert "await db_probe_ok(_DB_POOL)" in src or "await db_probe_ok(main._DB_POOL)" in src, (
        "readyz لا يفحص القاعدة ⇒ إيجابيّة كاذبة"
    )
