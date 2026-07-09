"""Auth MFA runtime helpers extracted from main.py.

This module intentionally imports ``main`` lazily inside helpers so the existing
routers that reference ``main._verify_caller_mfa`` / ``main.mfa_login_verify`` keep
working after main.py re-exports these functions. It keeps the security-sensitive
MFA lockout/audit/anti-replay logic out of the FastAPI bootstrap shell without
changing route contracts.
"""

from __future__ import annotations

import hashlib
import hmac
import os

import mfa_crypto


def _main():
    import main  # loaded service entrypoint; delayed to avoid bootstrap cycles

    return main


# ══════════════════════════════════════════════════════════════
# V29.5 — MFA production hardening: encryption-at-rest + recovery + DB lockout + audit.
# Pure crypto/lockout/recovery decisions live in ``mfa_crypto``; these helpers wire them
# to the DB rows. Compat path: encrypted secret preferred; legacy plaintext still works and
# is migrated on the next successful verify (never breaks an un-migrated user's login).
# ══════════════════════════════════════════════════════════════
def _ip_hash(ip: str | None) -> str | None:
    """Keyed HMAC of the IP (not a bare SHA-256 — a plain hash of an IPv4 is trivially
    reversible by dictionary). Key preference: MFA_AUDIT_HASH_KEY (dedicated) → _main().JWT_SECRET.

    V29.6.1: the static literal key is used **only outside production**. In production a
    forgeable static key would let anyone recompute an IP→hash table and de-anonymise the
    audit trail, so it is never reachable there. _main().JWT_SECRET is boot-enforced (≥32 chars) and
    always present in production, so a dedicated key being unset degrades to _main().JWT_SECRET, not
    to the literal. If somehow no keyed material exists in production ⇒ return None (audit still
    inserts with NULL ip_hash — best-effort forensics, never a forgeable hash)."""
    if not ip:
        return None
    key_material = os.getenv("MFA_AUDIT_HASH_KEY") or _main().JWT_SECRET
    if not key_material:
        if _main()._is_production():
            return None  # never hash under a forgeable static key in production
        key_material = "sahool-mfa-audit-dev"  # dev/test only (no _main().JWT_SECRET configured)
    return hmac.new(key_material.encode("utf-8"), ip.encode("utf-8"), hashlib.sha256).hexdigest()[
        :32
    ]


async def _emit_mfa_audit(
    *,
    user_id: int | None,
    event: str,
    outcome: str | None = None,
    actor_user_id: int | None = None,
    tenant_id: object | None = None,
    ip: str | None = None,
    request_id: str | None = None,
) -> None:
    """Append an MFA forensic event (best-effort — never breaks authentication)."""
    if not _main()._pool:
        return
    try:
        async with _main()._acquire() as conn:
            await conn.execute(
                "INSERT INTO mfa_audit_events "
                "(user_id, actor_user_id, tenant_id, event, outcome, ip_hash, request_id) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7)",
                user_id,
                actor_user_id,
                tenant_id,
                event,
                outcome,
                _ip_hash(ip),
                request_id,
            )
    except Exception as exc:  # noqa: BLE001 — التدقيق أفضل-جهد لا يكسر المصادقة
        _main().logger.warning("mfa audit insert failed: %s", type(exc).__name__)


async def _store_recovery_codes(user_id: int, tenant_id: object | None, codes: list[str]) -> None:
    """Rotate recovery codes: drop old, store fresh SHA-256 hashes (plaintext never stored)."""
    if not _main()._pool:
        return
    async with _main()._acquire() as conn, conn.transaction():
        # V29.6 — one transaction: a failed insert after the delete must not leave the
        # user with zero recovery codes (all-or-nothing rotation).
        await conn.execute("DELETE FROM mfa_recovery_codes WHERE user_id=$1", user_id)
        for code in codes:
            await conn.execute(
                "INSERT INTO mfa_recovery_codes (user_id, tenant_id, code_hash) VALUES ($1,$2,$3) "
                "ON CONFLICT (user_id, code_hash) DO NOTHING",
                user_id,
                tenant_id,
                mfa_crypto.hash_recovery_code(code),
            )


async def _consume_recovery_code(user_id: int, code: str) -> bool:
    """Atomically mark one unused recovery code used (one-time). Returns True on success."""
    if not _main()._pool or not code:
        return False
    async with _main()._acquire() as conn:
        marked = await conn.fetchval(
            "UPDATE mfa_recovery_codes SET used_at=NOW() "
            "WHERE user_id=$1 AND code_hash=$2 AND used_at IS NULL RETURNING id",
            user_id,
            mfa_crypto.hash_recovery_code(code),
        )
    return marked is not None


async def _register_mfa_failure(
    user_id: int,
    current_attempts: int | None = None,  # kept for signature compat; count is read in SQL
    *,
    event: str = "mfa_verify_failed",
    locked_event: str = "mfa_locked",
    tenant_id: object | None = None,
    ip: str | None = None,
    request_id: str | None = None,
) -> bool:
    """Atomically increment the DB failure counter and lock at the threshold. Returns
    whether the account is now locked. V29.6 — the increment + lock decision happen in one
    UPDATE (mfa_failed_attempts = mfa_failed_attempts + 1 … CASE) so concurrent failed
    attempts cannot lose increments (no read-modify-write race). Emits audit events."""
    locked_now = False
    if _main()._pool:
        threshold = mfa_crypto.max_failed_attempts()
        minutes = mfa_crypto.lockout_minutes()
        async with _main()._acquire() as conn:
            new_locked = await conn.fetchval(
                "UPDATE users SET "
                "  mfa_failed_attempts = mfa_failed_attempts + 1, "
                "  mfa_locked_until = CASE "
                "    WHEN mfa_failed_attempts + 1 >= $2 "
                "    THEN NOW() + make_interval(mins => $3) ELSE mfa_locked_until END "
                "WHERE id = $1 "
                "RETURNING (mfa_failed_attempts >= $2 AND mfa_locked_until IS NOT NULL)",
                user_id,
                threshold,
                minutes,
            )
            locked_now = bool(new_locked)
    await _emit_mfa_audit(
        user_id=user_id,
        event=event,
        outcome="failed",
        tenant_id=tenant_id,
        ip=ip,
        request_id=request_id,
    )
    if locked_now:
        await _emit_mfa_audit(
            user_id=user_id,
            event=locked_event,
            outcome="locked",
            tenant_id=tenant_id,
            ip=ip,
            request_id=request_id,
        )
    return locked_now


async def _mfa_reset_and_maybe_migrate(user_id: int, secret: str | None, *, migrate: bool) -> None:
    """On success: reset lockout counters + stamp verified; migrate plaintext→encrypted."""
    enc: str | None = None
    if migrate and secret and mfa_crypto.encryption_configured():
        try:
            enc = mfa_crypto.encrypt_secret(secret)
        except Exception as exc:  # noqa: BLE001 — الترحيل أفضل-جهد لا يمنع الدخول
            _main().logger.warning(
                "mfa plaintext→encrypted migrate skipped: %s", type(exc).__name__
            )
            enc = None
    if not _main()._pool:
        return
    async with _main()._acquire() as conn:
        if enc:
            await conn.execute(
                "UPDATE users SET mfa_failed_attempts=0, mfa_locked_until=NULL, "
                "mfa_last_verified_at=NOW(), encrypted_mfa_secret=$1, mfa_secret=NULL WHERE id=$2",
                enc,
                user_id,
            )
        else:
            await conn.execute(
                "UPDATE users SET mfa_failed_attempts=0, mfa_locked_until=NULL, "
                "mfa_last_verified_at=NOW() WHERE id=$1",
                user_id,
            )


async def _consume_totp_step(
    user_id, secret: str | None, code: str | None, *, valid_window: int = 1
) -> bool:
    """V29.7 — تحقّق TOTP مانع لإعادة التشغيل (anti-replay). يعيد True فقط إن طابق الرمز
    خطوةً زمنيّة **غير مُستهلَكة** (أحدث تماماً من آخر خطوة مقبولة). آمن ضدّ التسابق:
    التحديث ذرّيّ بشرط التقدّم؛ 0 صفوف ⇒ إعادة تشغيل/سباق ⇒ يُرفَض (fail-closed).

    يبقى منطق الاسترداد/القفل/التدقيق في المتّصِل — هذا يحلّ محلّ فحص pyotp المباشر فقط.
    """
    step = mfa_crypto.matched_totp_step(secret, code, valid_window=valid_window)
    if step is None or not _main()._pool:
        return False
    async with _main()._acquire() as conn:
        tag = await conn.execute(
            "UPDATE users SET mfa_last_totp_step=$1 "
            "WHERE id=$2 AND (mfa_last_totp_step IS NULL OR mfa_last_totp_step < $1)",
            int(step),
            user_id,
        )
    # asyncpg يُرجِع وسم أمر مثل 'UPDATE 1' — صفّ واحد ⇒ استُهلِكت الخطوة الآن (لا إعادة).
    # fail-closed: أيّ وسم غير نصّيّ/غير متوقّع ⇒ False (لا نقبل بلا تأكيد استهلاك).
    return bool(tag) and str(tag).rsplit(" ", 1)[-1] == "1"


async def mfa_login_verify(row, code: str, *, ip: str = "unknown", request_id: str | None = None):
    """Governed MFA check at login. Returns (ok: bool, reason: str). fail-closed.

    reason ∈ {totp, recovery} on success · {locked, key_missing, invalid} on failure.
    Handles: DB lockout gate, TOTP + one-time recovery-code verify, failure counter/lockout,
    reset-on-success, and legacy plaintext→encrypted migration on success.
    """
    user_id = row["id"]
    tenant_id = row["tenant_id"] if "tenant_id" in row else None
    if mfa_crypto.is_locked(row["mfa_locked_until"] if "mfa_locked_until" in row else None):
        await _emit_mfa_audit(
            user_id=user_id, event="mfa_locked", outcome="blocked", tenant_id=tenant_id, ip=ip
        )
        return False, "locked"
    try:
        secret = mfa_crypto.resolve_mfa_secret(
            row["encrypted_mfa_secret"] if "encrypted_mfa_secret" in row else None,
            row["mfa_secret"] if "mfa_secret" in row else None,
        )
    except mfa_crypto.MfaKeyMissing:
        await _emit_mfa_audit(
            user_id=user_id,
            event="mfa_verify_failed",
            outcome="key_missing",
            tenant_id=tenant_id,
            ip=ip,
        )
        return False, "key_missing"
    except mfa_crypto.MfaSecretUndecryptable:
        # V29.6 — corrupt ciphertext / rotated-away key ⇒ fail-closed with audit, never a 500.
        await _emit_mfa_audit(
            user_id=user_id,
            event="mfa_verify_failed",
            outcome="undecryptable",
            tenant_id=tenant_id,
            ip=ip,
        )
        return False, "undecryptable"
    used_plaintext = bool(
        (row["mfa_secret"] if "mfa_secret" in row else None)
        and not (row["encrypted_mfa_secret"] if "encrypted_mfa_secret" in row else None)
    )
    # V29.7 anti-replay: يستهلك الخطوة الزمنيّة ذرّيّاً — رمز صالح لا يُعاد استخدامه.
    ok = await _consume_totp_step(user_id, secret, code)
    via = "totp"
    if not ok and await _consume_recovery_code(user_id, code):
        ok, via = True, "recovery"
    if not ok:
        await _register_mfa_failure(user_id, tenant_id=tenant_id, ip=ip, request_id=request_id)
        return False, "invalid"
    await _mfa_reset_and_maybe_migrate(user_id, secret, migrate=used_plaintext)
    await _emit_mfa_audit(
        user_id=user_id,
        event="mfa_recovery_code_used" if via == "recovery" else "mfa_verify_success",
        outcome="success",
        tenant_id=tenant_id,
        ip=ip,
        request_id=request_id,
    )
    return True, via


# ── Admin endpoints ───────────────────────────────────────────
async def _verify_caller_mfa(
    admin_user_id: int, mfa_code: str | None, *, ip: str | None = None
) -> bool:
    """Step-up MFA for admin actions — now **governed** (V29.6): honours the same DB
    lockout as login and writes an audit trail (mfa_stepup_*), so a stolen admin session
    cannot brute-force step-up unaudited/unbounded.

    fail-closed: True only when the user exists, MFA is enabled, a secret resolves, the
    account is not locked, and the TOTP code is valid. Encrypted-secret aware with legacy
    plaintext fallback; missing key / undecryptable ⇒ fail-closed (never 500).
    """
    if not mfa_code or not _main()._pool:
        return False
    async with _main()._acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, tenant_id, mfa_enabled, mfa_secret, encrypted_mfa_secret, "
            "mfa_failed_attempts, mfa_locked_until FROM users WHERE id=$1",
            admin_user_id,
        )
    if not row or not row["mfa_enabled"]:
        return False
    tenant_id = row["tenant_id"] if "tenant_id" in row else None
    if mfa_crypto.is_locked(row["mfa_locked_until"] if "mfa_locked_until" in row else None):
        await _emit_mfa_audit(
            user_id=admin_user_id,
            event="mfa_stepup_locked",
            outcome="blocked",
            actor_user_id=admin_user_id,
            tenant_id=tenant_id,
            ip=ip,
        )
        return False
    try:
        secret = mfa_crypto.resolve_mfa_secret(
            row["encrypted_mfa_secret"] if "encrypted_mfa_secret" in row else None,
            row["mfa_secret"] if "mfa_secret" in row else None,
        )
    except (mfa_crypto.MfaKeyMissing, mfa_crypto.MfaSecretUndecryptable):
        await _emit_mfa_audit(
            user_id=admin_user_id,
            event="mfa_stepup_failed",
            outcome="crypto_degraded",
            actor_user_id=admin_user_id,
            tenant_id=tenant_id,
            ip=ip,
        )
        return False
    if not secret or not await _consume_totp_step(admin_user_id, secret, mfa_code):
        await _register_mfa_failure(
            admin_user_id,
            event="mfa_stepup_failed",
            locked_event="mfa_stepup_locked",
            tenant_id=tenant_id,
            ip=ip,
        )
        return False
    # success: clear the lockout counters + audit.
    async with _main()._acquire() as conn:
        await conn.execute(
            "UPDATE users SET mfa_failed_attempts=0, mfa_locked_until=NULL, "
            "mfa_last_verified_at=NOW() WHERE id=$1",
            admin_user_id,
        )
    await _emit_mfa_audit(
        user_id=admin_user_id,
        event="mfa_stepup_success",
        outcome="success",
        actor_user_id=admin_user_id,
        tenant_id=tenant_id,
        ip=ip,
    )
    return True
