"""اختبارات وحدة لـ step-up MFA على عمليّات admin الحسّاسة (change_role/deactivate).

تُغطّي المنطق النقيّ/المُحاكى دون قاعدة بيانات/Redis/شبكة:
  • قرار الفرض النقيّ _admin_stepup_required (الافتراضيّ False ⇒ CI أخضر).
  • منطق التحقّق _verify_caller_mfa (سرّ ناقص/MFA معطّل/رمز خاطئ ⇒ False).
  • حارس مصدريّ: change_role/deactivate يستدعيان فحص step-up.

الافتراضيّ (لا بيئة) ⇒ الفرض مُعطَّل ⇒ لا تغيير في السلوك (يبقى CI أخضر).

يُحمَّل services/auth/main.py عبر importlib؛ يُتخطّى الاختبار بأمان إذا غابت
تبعيّات الخدمة (fastapi/asyncpg…) في بيئة الوحدات بـCI.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import os
import sys
from unittest import mock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AUTH_DIR = os.path.join(ROOT, "services/auth")
_AUTH_MAIN = os.path.join(_AUTH_DIR, "main.py")


def _load_auth_main():
    """يُحمّل main.py الخاصّ بخدمة auth، ويتخطّى الاختبار إن غابت تبعيّاتها."""
    if _AUTH_DIR not in sys.path:
        sys.path.insert(0, _AUTH_DIR)
    existing = sys.modules.get("main")
    if existing is not None and not str(getattr(existing, "__file__", "")).startswith(_AUTH_DIR):
        # Other service tests sometimes import their own top-level main.py first.
        # Do not let that generic module-name collision make auth tests inspect
        # weather/raster/etc. instead of services/auth/main.py.
        sys.modules.pop("main", None)
    try:
        return importlib.import_module("main")
    except ImportError as e:  # تبعيّات الخدمة (fastapi…) غير مثبّتة في بيئة الوحدات بـCI
        pytest.skip(f"auth main.py غير قابل للاستيراد (تبعيّة ناقصة): {e}", allow_module_level=True)


main = _load_auth_main()


class TestAdminStepupRequired:
    @pytest.mark.unit
    @pytest.mark.security
    def test_default_is_off(self):
        # السلوك الافتراضيّ (CI/dev): بلا بيئة ⇒ لا فرض ⇒ change_role/deactivate بلا mfa_code.
        with mock.patch.dict(os.environ, {}, clear=True):
            assert main._admin_stepup_required() is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_enabled_via_explicit_flag(self):
        with mock.patch.dict(os.environ, {"ENFORCE_ADMIN_STEPUP_MFA": "true"}, clear=True):
            assert main._admin_stepup_required() is True

    @pytest.mark.unit
    @pytest.mark.security
    def test_enabled_via_production_env(self):
        with mock.patch.dict(os.environ, {"SAHOOL_ENV": "production"}, clear=True):
            assert main._admin_stepup_required() is True

    @pytest.mark.unit
    @pytest.mark.security
    def test_flag_is_case_insensitive(self):
        with mock.patch.dict(os.environ, {"ENFORCE_ADMIN_STEPUP_MFA": "TRUE"}, clear=True):
            assert main._admin_stepup_required() is True

    @pytest.mark.unit
    @pytest.mark.security
    def test_false_string_stays_off(self):
        with mock.patch.dict(os.environ, {"ENFORCE_ADMIN_STEPUP_MFA": "false"}, clear=True):
            assert main._admin_stepup_required() is False


class _FakeAcquire:
    """يحاكي async context manager لـ _pool.acquire()."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, row):
        self._row = row

    async def fetchrow(self, *a, **k):
        return self._row

    # V29.6 — step-up is now governed (lockout counter + audit + reset). V29.7 adds the
    # atomic TOTP anti-replay UPDATE which parses the asyncpg command tag, so the fake
    # returns a realistic "UPDATE 1" (one row consumed ⇒ step accepted, no replay).
    async def execute(self, *a, **k):
        return "UPDATE 1"

    async def fetchval(self, *a, **k):
        return None


class _FakePool:
    def __init__(self, row):
        self._row = row

    def acquire(self):
        return _FakeAcquire(_FakeConn(self._row))


def _run(coro):
    # asyncio.run: حلقة جديدة لكلّ نداء — متين في الدفعة (auto mode). get_event_loop
    # قد يُعيد حلقة مُغلقة من اختبار async سابق ⇒ فشل في الدفعة لا في العزل.
    return asyncio.run(coro)


class TestVerifyCallerMfa:
    @pytest.mark.unit
    @pytest.mark.security
    def test_absent_code_is_false(self):
        # رمز غائب ⇒ fail-closed، دون لمس القاعدة.
        with mock.patch.object(main, "_pool", _FakePool({"mfa_enabled": True, "mfa_secret": "X"})):
            assert _run(main._verify_caller_mfa(1, None)) is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_no_pool_is_false(self):
        with mock.patch.object(main, "_pool", None):
            assert _run(main._verify_caller_mfa(1, "123456")) is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_missing_user_is_false(self):
        with mock.patch.object(main, "_pool", _FakePool(None)):
            assert _run(main._verify_caller_mfa(1, "123456")) is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_mfa_not_enabled_is_false(self):
        row = {"mfa_enabled": False, "mfa_secret": "JBSWY3DPEHPK3PXP"}
        with mock.patch.object(main, "_pool", _FakePool(row)):
            assert _run(main._verify_caller_mfa(1, "123456")) is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_missing_secret_is_false(self):
        row = {"mfa_enabled": True, "mfa_secret": None}
        with mock.patch.object(main, "_pool", _FakePool(row)):
            assert _run(main._verify_caller_mfa(1, "123456")) is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_wrong_code_is_false(self):
        # سرّ صالح لكن رمز خاطئ ⇒ False.
        row = {"mfa_enabled": True, "mfa_secret": "JBSWY3DPEHPK3PXP"}
        with mock.patch.object(main, "_pool", _FakePool(row)):
            assert _run(main._verify_caller_mfa(1, "000000")) is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_correct_code_is_true(self):
        # سرّ صالح ورمز TOTP حاليّ صحيح ⇒ True (نفس تحقّق الدخول).
        import pyotp

        secret = "JBSWY3DPEHPK3PXP"
        row = {"mfa_enabled": True, "mfa_secret": secret}
        code = pyotp.TOTP(secret).now()
        with mock.patch.object(main, "_pool", _FakePool(row)):
            assert _run(main._verify_caller_mfa(1, code)) is True


def _change_role_handler():
    """يُرجِع مُعالِج change_role أينما كان (main.py أو routers/users.py بعد التفكيك)."""
    if hasattr(main, "change_role"):
        return main.change_role
    from routers.users import change_role  # noqa: PLC0415 — يُحلّ بعد import main

    return change_role


def _deactivate_handler():
    """يُرجِع مُعالِج deactivate_user أينما كان (main.py أو routers/users.py)."""
    if hasattr(main, "deactivate_user"):
        return main.deactivate_user
    from routers.users import deactivate_user  # noqa: PLC0415 — يُحلّ بعد import main

    return deactivate_user


class TestSourceGuard:
    """حارس مصدريّ: نقاط admin المُحوِّرة تشير لفحص step-up (لا انحدار صامت).

    بعد تفكيك مسارات auth انتقل change_role/deactivate_user إلى routers/users.py
    (سلوك محفوظ)؛ نمسح المصدر المُسلسَل (main.py + routers/*.py) ونحلّ المُعالِجات أينما
    وُجدت — دون إضعاف أيّ تأكيد أمنيّ (step-up + التوقيع + admin_op_mfa_denied).
    """

    @pytest.mark.unit
    @pytest.mark.security
    def test_endpoints_reference_stepup_check(self):
        from auth_route_source import auth_combined_source

        src = auth_combined_source(ROOT)
        # تعريف الدالّتين الحسّاستين موجود.
        assert "async def change_role(" in src
        assert "async def deactivate_user(" in src
        # كلاهما يستدعي الحارس النقيّ + المُتحقّق.
        assert src.count("_admin_stepup_required()") >= 2
        assert "_verify_caller_mfa(" in src
        assert "admin_op_mfa_denied" in src

    @pytest.mark.unit
    @pytest.mark.security
    def test_change_role_signature_accepts_mfa_header(self):
        sig = inspect.signature(_change_role_handler())
        assert "x_mfa_code" in sig.parameters
        assert "admin" in sig.parameters

    @pytest.mark.unit
    @pytest.mark.security
    def test_deactivate_signature_accepts_mfa_header(self):
        sig = inspect.signature(_deactivate_handler())
        assert "x_mfa_code" in sig.parameters
        assert "admin" in sig.parameters
