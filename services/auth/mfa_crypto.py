"""MFA production hardening — encryption-at-rest + recovery codes + lockout (V29.5).

Pure module: **no DB, no app, no FastAPI imports** — unit-testable in isolation. The
auth service (``main.py``) wires these helpers to the ``users`` / ``mfa_recovery_codes``
/ ``mfa_audit_events`` rows.

Design (fail-closed, no plaintext regressions):
- **Encryption at rest** — the TOTP secret is stored as ``encrypted_mfa_secret`` using
  Fernet (AES-128-CBC + HMAC) with a key from ``MFA_SECRET_ENCRYPTION_KEY`` (no default).
  Tokens are versioned (``v1:``) for future rotation; ``MFA_SECRET_DECRYPTION_KEYS`` (CSV)
  supplies retired keys for decrypt-only during rotation (MultiFernet).
- **Compat path** — ``resolve_mfa_secret`` prefers the encrypted column; if absent it
  falls back to a legacy plaintext ``mfa_secret`` so existing users keep logging in. If an
  encrypted secret exists but no key is configured, it raises ``MfaKeyMissing`` (fail-closed
  — never silently succeed/deny-wrong).
- **Recovery codes** — high-entropy, shown once, stored as SHA-256 hashes, one-time use.
- **Lockout** — pure decisions over DB-persisted ``mfa_failed_attempts`` / ``mfa_locked_until``.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta

_ENC_KEY_ENV = "MFA_SECRET_ENCRYPTION_KEY"
_ENC_DECRYPT_KEYS_ENV = "MFA_SECRET_DECRYPTION_KEYS"  # CSV of retired keys (decrypt-only, rotation)
_TOKEN_PREFIX = "v1:"  # version tag on stored ciphertext → key rotation / format evolution

RECOVERY_CODE_COUNT = 10


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        val = int(str(raw).strip()) if raw is not None and str(raw).strip() else default
    except ValueError:
        return default
    return val if val > 0 else default


def max_failed_attempts() -> int:
    return _int_env("MFA_MAX_FAILED_ATTEMPTS", 5)


def lockout_minutes() -> int:
    return _int_env("MFA_LOCKOUT_MINUTES", 15)


class MfaKeyMissing(RuntimeError):
    """Encrypted secret present (or setup requested) but no encryption key configured."""


class MfaSecretUndecryptable(RuntimeError):
    """Ciphertext could not be decrypted with any configured key (wrong/rotated key)."""


# ── encryption ──────────────────────────────────────────────────────────────
def _coerce_fernet_key(raw: str) -> bytes:
    """Accept a real Fernet key as-is; otherwise derive a deterministic 32-byte key.

    Operators may set an arbitrary passphrase; we never fail on format — a non-Fernet
    string is hashed (SHA-256) into a valid urlsafe-base64 32-byte Fernet key.
    """
    import base64

    from cryptography.fernet import Fernet

    candidate = raw.strip()
    try:
        Fernet(candidate.encode())  # validates length/base64
        return candidate.encode()
    except Exception:  # noqa: BLE001 — أيّ قيمة نصّيّة تُشتَقّ لمفتاح قانونيّ (لا تلفيق)
        digest = hashlib.sha256(candidate.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)


def _primary_key() -> str | None:
    raw = os.getenv(_ENC_KEY_ENV)
    return raw.strip() if raw and raw.strip() else None


def encryption_configured() -> bool:
    """True when a primary MFA encryption key is set (production requirement)."""
    return _primary_key() is not None


def _multifernet():
    from cryptography.fernet import Fernet, MultiFernet

    primary = _primary_key()
    if not primary:
        raise MfaKeyMissing(f"{_ENC_KEY_ENV} غير مضبوط — مطلوب لتشفير/فكّ سرّ MFA")
    keys = [_coerce_fernet_key(primary)]
    extra = os.getenv(_ENC_DECRYPT_KEYS_ENV, "") or ""
    keys.extend(_coerce_fernet_key(k) for k in extra.split(",") if k.strip())
    return MultiFernet([Fernet(k) for k in keys])


def encrypt_secret(plaintext_secret: str) -> str:
    """Encrypt a TOTP secret for at-rest storage. Raises MfaKeyMissing if no key."""
    token = _multifernet().encrypt(plaintext_secret.encode("utf-8")).decode("ascii")
    return _TOKEN_PREFIX + token


def decrypt_secret(stored: str) -> str:
    """Decrypt a stored (``v1:``-prefixed) TOTP secret. Raises on missing key / bad token."""
    from cryptography.fernet import InvalidToken

    body = stored[len(_TOKEN_PREFIX) :] if stored.startswith(_TOKEN_PREFIX) else stored
    try:
        return _multifernet().decrypt(body.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise MfaSecretUndecryptable("تعذّر فكّ سرّ MFA بالمفتاح الحاليّ") from exc


def resolve_mfa_secret(encrypted: str | None, plaintext: str | None) -> str | None:
    """Return the usable TOTP secret (compat), or None if the user has none.

    Priority: encrypted (decrypt) → legacy plaintext. Fail-closed: if an encrypted
    secret exists but no key is configured, raise MfaKeyMissing (never fall back to
    a stale plaintext, never silently pass).
    """
    if encrypted:
        if not encryption_configured():
            raise MfaKeyMissing("سرّ MFA مشفّر لكن لا مفتاح مُهيَّأ — fail-closed")
        return decrypt_secret(encrypted)
    if plaintext:
        return plaintext
    return None


# ── recovery codes ──────────────────────────────────────────────────────────
def generate_recovery_codes(n: int = RECOVERY_CODE_COUNT) -> list[str]:
    """n high-entropy one-time codes, formatted ``XXXXX-XXXXX`` (shown once)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous 0/O/1/I
    out: list[str] = []
    for _ in range(max(1, n)):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        out.append(f"{raw[:5]}-{raw[5:]}")
    return out


def normalize_recovery_code(code: str) -> str:
    return "".join(ch for ch in str(code).upper() if ch.isalnum())


def hash_recovery_code(code: str) -> str:
    """SHA-256 of the normalized code (codes are high-entropy → fast hash is sufficient)."""
    return hashlib.sha256(normalize_recovery_code(code).encode("utf-8")).hexdigest()


def verify_recovery_code(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_recovery_code(code), str(code_hash or ""))


# ── lockout (pure decisions over DB-persisted counters) ─────────────────────
def is_locked(locked_until: datetime | None, now: datetime | None = None) -> bool:
    if locked_until is None:
        return False
    ref = now or datetime.now(UTC)
    lu = locked_until if locked_until.tzinfo else locked_until.replace(tzinfo=UTC)
    return lu > ref


def register_failure(
    current_attempts: int, now: datetime | None = None
) -> tuple[int, datetime | None]:
    """Return (new_attempts, locked_until|None) after one failed MFA attempt."""
    ref = now or datetime.now(UTC)
    new_attempts = max(0, int(current_attempts or 0)) + 1
    if new_attempts >= max_failed_attempts():
        return new_attempts, ref + timedelta(minutes=lockout_minutes())
    return new_attempts, None
