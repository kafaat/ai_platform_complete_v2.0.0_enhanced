"""حارس دور قاعدة البيانات المشترَك (shared/db_role_guard) — FINDING-001.

يثبت اللينشين: ترفض الخدمة الإقلاع (fail-closed افتراضيّاً) إن اتّصلت بدور يتجاوز RLS
(superuser/BYPASSRLS)، ما لم يُعطَّل صراحةً للتطوير المحلّيّ. اختبار وحدة نقيّ + فحص
الدالّة async بمحاكاة اتّصال asyncpg.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.db_role_guard import (  # noqa: E402
    assert_db_role_rls_safe,
    assert_dsn_role_rls_safe,
    enforcement_active,
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

    async def test_probe_error_does_not_block(self):
        """تعذّر الفحص نفسه ⇒ لا يحجب الإقلاع (best-effort)."""
        await assert_db_role_rls_safe(_FakeConn(True, True, raise_on_fetch=True), service="t")

    async def test_dsn_helper_no_dsn_is_noop(self):
        await assert_dsn_role_rls_safe("", service="t")  # no raise, no connect
