"""S3/S4 (تدقيق 2026-11-01) — قفل MFA وحالة «مُفعَّل سلفاً» في /mfa/activate و/mfa/disable.

S3: ``/v1/auth/mfa/activate`` كان بلا حدّ للتخمين (تدقيق فقط، لا عدّاد) وبلا فحص «مُفعَّل
سلفاً» ⇒ جلسة مسروقة تُصدِر رموز استرداد جديدة وتُصفّر عدّاد القفل.
S4: ``/v1/auth/mfa/disable`` كان يعدّ المحاولات ولا يطبّق القفل ⇒ رمز صحيح أثناء القفل عطّل MFA.

يختبر **قرار المُعالِج** لا سلوك قاعدة: صفّ المستخدم يُحقَن عبر ``_load_mfa_row`` ومساعِدات
MFA تُرقَّع، و``_acquire`` سلكُ تعثّر — بلوغُه يعني أنّ البوّابات سمحت بالكتابة. لا بديلَ اتّصال
(FAKE-CONNECTION-ENFORCES-NOTHING-01): SQL القفل نفسه مُغطّى في mfa_runtime/التكامل.
يتخطّى بأمان إن تعذّر استيراد خدمة auth (تبعيّات ناقصة في بيئة خفيفة).
"""

from __future__ import annotations

import asyncio
import importlib
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest

from tests_v9.service_module import load_service_main

pytestmark = [pytest.mark.unit, pytest.mark.security]

main = load_service_main(
    "services/auth", required_attrs=("MfaCodeRequest", "_register_mfa_failure")
)
mfa = importlib.import_module("routers.mfa")

_SECRET = "JBSWY3DPEHPK3PXP"


class _ReachedWrite(Exception):
    """البوّابات سمحت للمُعالِج ببلوغ الكتابة (UPDATE users …)."""


def _tripwire():
    raise _ReachedWrite


def _row(*, enabled: bool, locked_until=None):
    return {
        "mfa_secret": _SECRET,
        "encrypted_mfa_secret": None,
        "mfa_enabled": enabled,
        "mfa_locked_until": locked_until,
        "tenant_id": "t1",
    }


def _call(handler, row, *, code_ok: bool):
    """يستدعي المُعالِج ويُعيد (الاستثناء، رقعة عدّاد الفشل، رقعة فحص الرمز)."""
    consume = mock.AsyncMock(return_value=code_ok)
    failure = mock.AsyncMock(return_value=False)
    with (
        mock.patch.object(mfa, "_load_mfa_row", mock.AsyncMock(return_value=row)),
        mock.patch.object(main, "_consume_totp_step", consume),
        mock.patch.object(main, "_register_mfa_failure", failure),
        mock.patch.object(main, "_emit_mfa_audit", mock.AsyncMock()),
        mock.patch.object(main, "_acquire", _tripwire),
    ):
        try:
            asyncio.run(handler(main.MfaCodeRequest(code="123456"), {"sub": "7"}))
        except Exception as exc:  # noqa: BLE001 — يُعاد للتأكيد على صنفه
            return exc, failure, consume
    return None, failure, consume


def _future():
    return datetime.now(UTC) + timedelta(minutes=10)


@pytest.fixture
def mfa_key(monkeypatch):
    # السرّ النصّيّ القديم يُرحَّل مشفّراً عند التفعيل ⇒ يلزم مفتاح (Fernet صالح).
    from cryptography.fernet import Fernet

    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", Fernet.generate_key().decode())


# ── S3: /mfa/activate ─────────────────────────────────────────────
def test_activate_refuses_when_mfa_is_already_enabled_even_with_a_valid_code(mfa_key):
    exc, _failure, consume = _call(mfa.mfa_activate, _row(enabled=True), code_ok=True)
    assert isinstance(exc, main.HTTPException) and exc.status_code == 400, (
        f"رموز استرداد جديدة لحساب MFA مفعّل سلفاً: {exc!r}"
    )
    consume.assert_not_awaited()


def test_activate_wrong_code_feeds_the_shared_lockout_counter():
    exc, failure, _ = _call(mfa.mfa_activate, _row(enabled=False), code_ok=False)
    assert isinstance(exc, main.HTTPException) and exc.status_code == 400
    failure.assert_awaited_once()
    assert failure.await_args.kwargs["event"] == "mfa_activate_failed"


def test_activate_is_refused_during_lockout_even_with_a_valid_code(mfa_key):
    row = _row(enabled=False, locked_until=_future())
    exc, _failure, consume = _call(mfa.mfa_activate, row, code_ok=True)
    assert isinstance(exc, main.HTTPException) and exc.status_code == 429, repr(exc)
    consume.assert_not_awaited()  # لا يُستهلَك رمز أثناء القفل


def test_activate_with_a_valid_code_and_no_lock_reaches_the_write(mfa_key):
    exc, failure, _ = _call(mfa.mfa_activate, _row(enabled=False), code_ok=True)
    assert isinstance(exc, _ReachedWrite), repr(exc)
    failure.assert_not_awaited()


# ── S4: /mfa/disable ──────────────────────────────────────────────
def test_disable_is_refused_during_lockout_even_with_a_valid_code():
    row = _row(enabled=True, locked_until=_future())
    exc, _failure, consume = _call(mfa.mfa_disable, row, code_ok=True)
    assert isinstance(exc, main.HTTPException) and exc.status_code == 429, (
        f"MFA عُطِّل أثناء القفل: {exc!r}"
    )
    consume.assert_not_awaited()


def test_disable_after_lock_expiry_with_a_valid_code_reaches_the_write():
    row = _row(enabled=True, locked_until=datetime.now(UTC) - timedelta(minutes=1))
    exc, failure, _ = _call(mfa.mfa_disable, row, code_ok=True)
    assert isinstance(exc, _ReachedWrite), repr(exc)
    failure.assert_not_awaited()


def test_disable_wrong_code_still_feeds_the_lockout_counter():
    exc, failure, _ = _call(mfa.mfa_disable, _row(enabled=True), code_ok=False)
    assert isinstance(exc, main.HTTPException) and exc.status_code == 400
    failure.assert_awaited_once()
