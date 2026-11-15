"""حارس دور قاعدة البيانات المشترَك (shared/db_role_guard) — FINDING-001.

يثبت اللينشين: ترفض الخدمة الإقلاع (fail-closed افتراضيّاً) إن اتّصلت بدور يتجاوز RLS
(superuser/BYPASSRLS)، ما لم يُعطَّل صراحةً للتطوير المحلّيّ. اختبار وحدة نقيّ + فحص
الدالّة async بمحاكاة اتّصال asyncpg.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.db_role_guard import (  # noqa: E402
    DEFAULT_PROBE_TIMEOUT_SECONDS,
    PROBE_TIMEOUT_ENV,
    assert_db_role_rls_safe,
    assert_dsn_role_rls_safe,
    enforcement_active,
    probe_timeout_seconds,
    role_can_bypass_rls,
    role_guard_message,
    should_refuse_startup,
)


class TestPureLogic:
    def test_superuser_bypasses(self):
        assert role_can_bypass_rls(True, False) is True

    def test_bypassrls_bypasses(self):
        assert role_can_bypass_rls(False, True) is True

    def test_restricted_role_safe(self):
        assert role_can_bypass_rls(False, False) is False

    def test_enforcement_default_on(self):
        # الغياب التامّ ⇒ يُفرَض (fail-closed) — جوهر الإصلاح.
        assert enforcement_active(None, None) is True

    def test_escape_hatch_disables(self):
        for v in ("1", "true", "YES", "on"):
            assert enforcement_active(v, None) is False

    def test_explicit_enforce_off_disables(self):
        for v in ("0", "false", "no", "off"):
            assert enforcement_active(None, v) is False

    def test_enforce_on_does_not_disable(self):
        assert enforcement_active(None, "1") is True

    def test_refuse_only_when_unsafe_and_enforced(self):
        assert should_refuse_startup(True, True) is True
        assert should_refuse_startup(True, False) is False
        assert should_refuse_startup(False, True) is False

    def test_message_names_role_and_fix(self):
        msg = role_guard_message(True, False, refused=True, service="auth")
        assert "superuser" in msg
        assert "sahool_app" in msg  # يسمّي الإصلاح
        assert "auth" in msg


class _FakeConn:
    def __init__(self, rolsuper, rolbypassrls, raise_on_fetch=False):
        self._row = {"rolsuper": rolsuper, "rolbypassrls": rolbypassrls}
        self._raise = raise_on_fetch
        self.closed = False

    async def fetchrow(self, _sql):
        if self._raise:
            raise RuntimeError("probe boom")
        return self._row

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
class TestAsyncGuard:
    async def test_refuses_on_superuser_default(self):
        """دور superuser + الغياب (fail-closed) ⇒ RuntimeError (رفض الإقلاع)."""
        os.environ.pop("SAHOOL_ALLOW_RLS_BYPASS_ROLE", None)
        os.environ.pop("SAHOOL_ENFORCE_RLS_ROLE", None)
        with pytest.raises(RuntimeError):
            await assert_db_role_rls_safe(_FakeConn(True, False), service="t")

    async def test_allows_restricted_role(self):
        """دور مقيّد (NOBYPASSRLS) ⇒ لا رفض."""
        await assert_db_role_rls_safe(_FakeConn(False, False), service="t")  # no raise

    async def test_escape_hatch_allows_superuser(self):
        """مهرب التطوير المحلّيّ يسمح بدور superuser (تحذير لا رفض)."""
        os.environ["SAHOOL_ALLOW_RLS_BYPASS_ROLE"] = "1"
        try:
            await assert_db_role_rls_safe(_FakeConn(True, True), service="t")  # no raise
        finally:
            os.environ.pop("SAHOOL_ALLOW_RLS_BYPASS_ROLE", None)

    async def test_dsn_helper_no_dsn_is_noop(self):
        await assert_dsn_role_rls_safe("", service="t")  # no raise, no connect


# ── LIFE-01 في الحارس المشترَك: دورٌ لم تُثبَت سلامته غير آمن ما دام الفرض مُفعَّلاً ──
# كان ``except Exception: debug; return`` و``row is None: return`` يُكمِلان إقلاع الخدمات
# السبع (auth/soil/erp-bridge/raster/guardrails/actuator/market-mcp) على دورٍ مجهول.


class _ProbeConn:
    """اتّصالٌ مزيّف: ``fetchrow`` يُرجِع ``outcome`` أو يرفعه أو يتعلّق ("hang")."""

    def __init__(self, outcome):
        self.outcome = outcome

    async def fetchrow(self, _sql):
        if self.outcome == "hang":
            await asyncio.Event().wait()
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class _ProbePool:
    def __init__(self, outcome):
        self.conn = _ProbeConn(outcome)
        self.released = False

    @contextlib.asynccontextmanager
    async def acquire(self):
        try:
            yield self.conn
        finally:
            self.released = True


@pytest.fixture
def enforced(monkeypatch):
    monkeypatch.delenv("SAHOOL_ALLOW_RLS_BYPASS_ROLE", raising=False)
    monkeypatch.delenv("SAHOOL_ENFORCE_RLS_ROLE", raising=False)


_UNVERIFIABLE = [
    pytest.param(RuntimeError("probe boom"), id="probe-error"),
    pytest.param(PermissionError("denied"), id="permission"),
    pytest.param(None, id="no-row"),
]


@pytest.mark.parametrize("outcome", _UNVERIFIABLE)
@pytest.mark.parametrize("via_pool", [False, True], ids=["conn", "pool"])
async def test_unverifiable_role_refuses_startup_under_enforcement(enforced, outcome, via_pool):
    target = _ProbePool(outcome) if via_pool else _ProbeConn(outcome)
    with pytest.raises(RuntimeError, match=r"\[svc\] RLS database role verification"):
        await assert_db_role_rls_safe(target, service="svc")
    if via_pool:
        assert target.released, "the probe connection goes back to the pool even on refusal"


async def test_stalled_probe_is_bounded_and_refuses(enforced, monkeypatch):
    monkeypatch.setenv(PROBE_TIMEOUT_ENV, "0.05")
    with pytest.raises(RuntimeError, match="verification failed .TimeoutError."):
        await asyncio.wait_for(assert_db_role_rls_safe(_ProbePool("hang"), service="svc"), 5)


def test_probe_timeout_has_a_bounded_default(monkeypatch):
    monkeypatch.delenv(PROBE_TIMEOUT_ENV, raising=False)
    assert 0 < probe_timeout_seconds() == DEFAULT_PROBE_TIMEOUT_SECONDS <= 30
    for bad in ("0", "-1", "soon"):
        monkeypatch.setenv(PROBE_TIMEOUT_ENV, bad)
        assert probe_timeout_seconds() == DEFAULT_PROBE_TIMEOUT_SECONDS


async def test_cancellation_is_not_turned_into_a_refusal(enforced):
    with pytest.raises(asyncio.CancelledError):
        await assert_db_role_rls_safe(_ProbeConn(asyncio.CancelledError()), service="svc")


@pytest.mark.parametrize("outcome", _UNVERIFIABLE)
@pytest.mark.parametrize(
    "bypass_env",
    [("SAHOOL_ALLOW_RLS_BYPASS_ROLE", "1"), ("SAHOOL_ENFORCE_RLS_ROLE", "0")],
    ids=["allow-bypass", "enforce-off"],
)
async def test_explicit_bypass_starts_on_an_unverifiable_role_with_a_warning(
    monkeypatch, caplog, outcome, bypass_env
):
    monkeypatch.delenv("SAHOOL_ALLOW_RLS_BYPASS_ROLE", raising=False)
    monkeypatch.delenv("SAHOOL_ENFORCE_RLS_ROLE", raising=False)
    monkeypatch.setenv(*bypass_env)
    with caplog.at_level(logging.WARNING, logger="svc"):
        assert await assert_db_role_rls_safe(_ProbeConn(outcome), service="svc") is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and r.name == "svc"]
    assert len(warnings) == 1 and "RLS" in warnings[0].getMessage()


async def test_probe_failure_logs_only_the_exception_class(monkeypatch, caplog):
    monkeypatch.setenv("SAHOOL_ALLOW_RLS_BYPASS_ROLE", "1")
    secret = "postgresql://sahool_app:hunter2@db/sahool"
    with caplog.at_level(logging.DEBUG):
        await assert_db_role_rls_safe(_ProbeConn(OSError(secret)), service="svc")
    assert "OSError" in caplog.text and "hunter2" not in caplog.text


async def test_dsn_helper_refuses_an_unverifiable_role_and_closes_its_connection(
    enforced, monkeypatch
):
    import asyncpg

    conns, kwargs_seen = [], []

    class _Conn(_ProbeConn):
        closed = False

        async def close(self):
            self.closed = True

    async def connect(_dsn, **kwargs):
        kwargs_seen.append(kwargs)
        conns.append(_Conn(None))
        return conns[-1]

    monkeypatch.setattr(asyncpg, "connect", connect)
    with pytest.raises(RuntimeError, match="returned no role"):
        await assert_dsn_role_rls_safe("postgresql://x/db", service="svc")
    assert conns[0].closed
    assert kwargs_seen[0]["timeout"] == probe_timeout_seconds(), "the probe connect is bounded"


async def test_dsn_helper_unreachable_database_stays_best_effort_but_warns(
    enforced, monkeypatch, caplog
):
    """raster/guardrails start DB-less and connect per call; an absent DB is not a role."""
    import asyncpg

    async def connect(_dsn, **_kwargs):
        raise ConnectionRefusedError(111, "postgresql://u:hunter2@db refused")

    monkeypatch.setattr(asyncpg, "connect", connect)
    with caplog.at_level(logging.WARNING, logger="svc"):
        assert await assert_dsn_role_rls_safe("postgresql://x/db", service="svc") is None
    assert "ConnectionRefusedError" in caplog.text and "hunter2" not in caplog.text
