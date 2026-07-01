"""تحقّق V29.5 — وحدة تصلّب MFA النقيّة (mfa_crypto): تشفير + رموز استرداد + قفل.

منطق صرف بلا DB/تطبيق — وظيفة Unit Tests. يغطّي:
- roundtrip تشفير/فكّ + وسم إصدار (v1:).
- resolve_mfa_secret: تفضيل المشفّر · سقوط للنصّ · fail-closed عند مفتاح مفقود لسرّ مشفّر.
- مفتاح خاطئ ⇒ MfaSecretUndecryptable (لا نجاح كاذب).
- رموز الاسترداد: توليد/تجزئة/تحقّق + تطبيع + رفض الخاطئ.
- القفل: is_locked + register_failure (عتبة + عدم قفل قبلها).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_AUTH = Path(__file__).resolve().parents[1] / "services" / "auth"
if str(_AUTH) not in sys.path:
    sys.path.insert(0, str(_AUTH))

import mfa_crypto as M  # noqa: E402

_KEY = "unit-test-mfa-encryption-key-passphrase"


# ── تشفير ────────────────────────────────────────────────────────────────────
def test_encrypt_decrypt_roundtrip_and_version_tag(monkeypatch):
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", _KEY)
    token = M.encrypt_secret("JBSWY3DPEHPK3PXP")
    assert token.startswith("v1:")
    assert M.decrypt_secret(token) == "JBSWY3DPEHPK3PXP"


def test_encryption_configured_reflects_env(monkeypatch):
    monkeypatch.delenv("MFA_SECRET_ENCRYPTION_KEY", raising=False)
    assert M.encryption_configured() is False
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", _KEY)
    assert M.encryption_configured() is True


def test_wrong_key_cannot_decrypt(monkeypatch):
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", _KEY)
    token = M.encrypt_secret("SECRET123")
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", "a-totally-different-key")
    with pytest.raises(M.MfaSecretUndecryptable):
        M.decrypt_secret(token)


# ── V29.6 — production key quality ───────────────────────────────────────────
def test_production_refuses_derived_key(monkeypatch):
    # مفتاح ضعيف (ليس Fernet) في الإنتاج بلا سماح صريح ⇒ fail-closed.
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.delenv("MFA_ALLOW_DERIVED_KEY", raising=False)
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", "weak-passphrase")
    with pytest.raises(M.MfaKeyMissing):
        M.encrypt_secret("SECRET123")


def test_production_allows_derived_key_with_optin(monkeypatch):
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setenv("MFA_ALLOW_DERIVED_KEY", "1")
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", "weak-passphrase")
    token = M.encrypt_secret("SECRET123")
    assert M.decrypt_secret(token) == "SECRET123"


def test_production_accepts_valid_fernet_key(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.delenv("MFA_ALLOW_DERIVED_KEY", raising=False)
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = M.encrypt_secret("SECRET123")
    assert M.decrypt_secret(token) == "SECRET123"


def test_development_allows_derived_key(monkeypatch):
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.delenv("MFA_ALLOW_DERIVED_KEY", raising=False)
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", "weak-passphrase")
    token = M.encrypt_secret("SECRET123")
    assert M.decrypt_secret(token) == "SECRET123"


# ── مسار التوافق (resolve) ──────────────────────────────────────────────────
def test_resolve_prefers_encrypted(monkeypatch):
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", _KEY)
    enc = M.encrypt_secret("ENCSECRET")
    assert M.resolve_mfa_secret(enc, "PLAINLEGACY") == "ENCSECRET"


def test_resolve_falls_back_to_plaintext(monkeypatch):
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", _KEY)
    assert M.resolve_mfa_secret(None, "PLAINLEGACY") == "PLAINLEGACY"


def test_resolve_none_when_no_secret(monkeypatch):
    monkeypatch.setenv("MFA_SECRET_ENCRYPTION_KEY", _KEY)
    assert M.resolve_mfa_secret(None, None) is None


def test_resolve_fail_closed_encrypted_without_key(monkeypatch):
    # سرّ مشفّر موجود لكن لا مفتاح ⇒ لا سقوط صامت، لا نجاح خاطئ.
    monkeypatch.delenv("MFA_SECRET_ENCRYPTION_KEY", raising=False)
    with pytest.raises(M.MfaKeyMissing):
        M.resolve_mfa_secret("v1:sometoken", "PLAINLEGACY")


def test_legacy_plaintext_login_unaffected_without_key(monkeypatch):
    # مستخدم قديم بنصّ فقط يبقى يعمل حتى بلا مفتاح (لا نكسر الدخول).
    monkeypatch.delenv("MFA_SECRET_ENCRYPTION_KEY", raising=False)
    assert M.resolve_mfa_secret(None, "PLAINLEGACY") == "PLAINLEGACY"


# ── رموز الاسترداد ───────────────────────────────────────────────────────────
def test_recovery_codes_generated_count_and_shape():
    codes = M.generate_recovery_codes()
    assert len(codes) == M.RECOVERY_CODE_COUNT == 10
    assert all("-" in c and len(c.replace("-", "")) == 10 for c in codes)
    assert len(set(codes)) == len(codes)  # فريدة


def test_recovery_hash_verify_and_normalization():
    code = M.generate_recovery_codes(1)[0]
    h = M.hash_recovery_code(code)
    assert M.verify_recovery_code(code, h) is True
    # تطبيع: بلا شرطات + حالة أحرف مختلفة يقبلها.
    assert M.verify_recovery_code(code.lower().replace("-", ""), h) is True
    assert M.verify_recovery_code("WRONG-CODE0", h) is False
    assert M.verify_recovery_code(code, "") is False


# ── القفل ────────────────────────────────────────────────────────────────────
def test_is_locked_boundaries():
    now = datetime.now(UTC)
    assert M.is_locked(None, now) is False
    assert M.is_locked(now - timedelta(minutes=1), now) is False  # انتهى القفل
    assert M.is_locked(now + timedelta(minutes=1), now) is True  # ما زال مقفلاً


def test_register_failure_locks_at_threshold(monkeypatch):
    monkeypatch.setenv("MFA_MAX_FAILED_ATTEMPTS", "5")
    monkeypatch.setenv("MFA_LOCKOUT_MINUTES", "15")
    now = datetime.now(UTC)
    att, lock = M.register_failure(0, now)
    assert att == 1 and lock is None
    att, lock = M.register_failure(4, now)  # المحاولة الخامسة
    assert att == 5 and lock is not None
    assert lock >= now + timedelta(minutes=14)


def test_register_failure_no_lock_before_threshold(monkeypatch):
    monkeypatch.setenv("MFA_MAX_FAILED_ATTEMPTS", "5")
    now = datetime.now(UTC)
    for prev in range(0, 4):
        att, lock = M.register_failure(prev, now)
        assert att == prev + 1 and lock is None
