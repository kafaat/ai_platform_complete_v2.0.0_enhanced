"""تحقّق تكامل V29.5 — تصلّب MFA على Postgres حقيقيّ (مثل v127، لا mock/SQLite).

يغطّي بنود المستخدم الإلزاميّة:
- الترحيل مُطبَّق (أعمدة/جداول MFA موجودة).
- setup يخزّن السرّ **مشفّراً** لا نصّاً؛ activate يُصدِر رموز استرداد.
- تسجيل دخول MFA صحيح ⇒ نجاح.
- مستخدم قديم بسرّ نصّيّ يظلّ يسجّل الدخول، وبعد النجاح يُرحَّل إلى مشفّر (نصّ ⇒ NULL).
- رمز استرداد يُستهلَك مرّة واحدة فقط.
- القفل يُثبَّت في DB (mfa_locked_until) بعد تجاوز الحدّ (يبقى عبر الطلبات).
- صفوف تدقيق MFA تُدرَج.

يعمل بـ``pytest -m integration`` (يتخطّى إن لا DB) — يُشغَّل في وظيفة CI Integration.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql://sahool_user@/sahool?host=/tmp/pgrun")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "z" * 48)
os.environ.setdefault("SAHOOL_ENV", "development")
# مفتاح تشفير MFA مطلوب قبل تحميل الخدمة (تشفير عند الراحة).
os.environ.setdefault("MFA_SECRET_ENCRYPTION_KEY", "integration-mfa-key-" + "x" * 24)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

pytestmark = pytest.mark.integration


def _db_available() -> bool:
    try:
        import asyncpg

        async def _ping():
            c = await asyncpg.connect(os.environ["DATABASE_URL"])
            await c.close()

        asyncio.run(_ping())
        return True
    except Exception:
        return False


def _load_auth_main():
    sys.path.insert(0, os.path.join(ROOT, "services/auth"))
    sys.path.insert(0, ROOT)
    spec = importlib.util.spec_from_file_location(
        "auth_main_mfa", os.path.join(ROOT, "services/auth/main.py")
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["auth_main_mfa"] = m
    spec.loader.exec_module(m)
    return m


async def _fetchrow(sql: str, *args):
    import asyncpg

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        return await conn.fetchrow(sql, *args)
    finally:
        await conn.close()


async def _execute(sql: str, *args):
    import asyncpg

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        return await conn.execute(sql, *args)
    finally:
        await conn.close()


def _register_and_token(client, email, pw):
    r = client.post(
        "/auth/register",
        json={"email": email, "password": pw, "full_name": "مزارع MFA", "role": "owner"},
    )
    assert r.status_code == 201, f"register {r.status_code}: {r.text[:160]}"
    return r.json()["access_token"]


@pytest.mark.integration
def test_mfa_hardening_end_to_end():
    if not _db_available():
        pytest.skip("DATABASE_URL غير متاح — اختبار تكامل")
    import pyotp
    from fastapi.testclient import TestClient

    m = _load_auth_main()
    pw = "S3cure-Pass!2026"
    email = f"mfa_{uuid.uuid4().hex[:8]}@sahool.ye"

    with TestClient(m.app, raise_server_exceptions=False) as c:
        tok = _register_and_token(c, email, pw)
        auth = {"Authorization": f"Bearer {tok}"}

        # ── setup: السرّ يُخزَّن مشفّراً لا نصّاً ──
        r = c.post("/auth/mfa/setup", headers=auth)
        assert r.status_code == 200, f"setup {r.status_code}: {r.text[:160]}"
        secret = r.json()["secret"]
        row = asyncio.run(
            _fetchrow("SELECT mfa_secret, encrypted_mfa_secret FROM users WHERE email=$1", email)
        )
        assert row["encrypted_mfa_secret"] and str(row["encrypted_mfa_secret"]).startswith("v1:")
        assert row["mfa_secret"] is None  # لا سرّ نصّيّ جديد

        # ── activate: يُصدِر رموز استرداد (مرّة واحدة) ──
        r = c.post("/auth/mfa/activate", headers=auth, json={"code": pyotp.TOTP(secret).now()})
        assert r.status_code == 200, f"activate {r.status_code}: {r.text[:160]}"
        recovery_codes = r.json()["recovery_codes"]
        assert len(recovery_codes) == 10
        # تُخزَّن كـhash فقط (لا نصّ في DB).
        hashed = asyncio.run(
            _fetchrow(
                "SELECT COUNT(*) AS n FROM mfa_recovery_codes rc "
                "JOIN users u ON u.id = rc.user_id WHERE u.email=$1 AND rc.used_at IS NULL",
                email,
            )
        )
        assert hashed["n"] == 10

        # ── login بـTOTP صحيح ⇒ نجاح ──
        r = c.post(
            "/auth/login",
            json={"email": email, "password": pw, "mfa_code": pyotp.TOTP(secret).now()},
        )
        assert r.status_code == 200, f"mfa login {r.status_code}: {r.text[:160]}"

        # ── رمز استرداد يُستهلَك مرّة واحدة فقط ──
        rc0 = recovery_codes[0]
        r = c.post("/auth/login", json={"email": email, "password": pw, "mfa_code": rc0})
        assert r.status_code == 200, f"recovery login {r.status_code}: {r.text[:160]}"
        r = c.post("/auth/login", json={"email": email, "password": pw, "mfa_code": rc0})
        assert r.status_code == 401, "إعادة استخدام رمز الاسترداد يجب أن تفشل"

        # ── القفل يُثبَّت في DB بعد تجاوز الحدّ ──
        last = None
        for _ in range(5):
            last = c.post(
                "/auth/login", json={"email": email, "password": pw, "mfa_code": "000000"}
            )
        assert last is not None and last.status_code in (401, 429)
        locked = asyncio.run(_fetchrow("SELECT mfa_locked_until FROM users WHERE email=$1", email))
        assert locked["mfa_locked_until"] is not None  # دائم في DB (يعبر الطلبات)

        # ── تدقيق MFA مُدرَج ──
        audit = asyncio.run(
            _fetchrow(
                "SELECT COUNT(*) AS n FROM mfa_audit_events ev "
                "JOIN users u ON u.id = ev.user_id WHERE u.email=$1",
                email,
            )
        )
        assert audit["n"] >= 1

        # ── مستخدم قديم بسرّ نصّيّ: يظلّ يسجّل الدخول ثمّ يُرحَّل إلى مشفّر ──
        legacy_email = f"legacy_{uuid.uuid4().hex[:8]}@sahool.ye"
        _register_and_token(c, legacy_email, pw)
        legacy_secret = pyotp.random_base32()
        asyncio.run(
            _execute(
                "UPDATE users SET mfa_enabled=TRUE, mfa_secret=$1, encrypted_mfa_secret=NULL, "
                "mfa_failed_attempts=0, mfa_locked_until=NULL WHERE email=$2",
                legacy_secret,
                legacy_email,
            )
        )
        r = c.post(
            "/auth/login",
            json={
                "email": legacy_email,
                "password": pw,
                "mfa_code": pyotp.TOTP(legacy_secret).now(),
            },
        )
        assert r.status_code == 200, f"legacy plaintext login {r.status_code}: {r.text[:160]}"
        migrated = asyncio.run(
            _fetchrow(
                "SELECT mfa_secret, encrypted_mfa_secret FROM users WHERE email=$1", legacy_email
            )
        )
        assert migrated["encrypted_mfa_secret"] and str(
            migrated["encrypted_mfa_secret"]
        ).startswith("v1:")
        assert migrated["mfa_secret"] is None  # النصّ مُسِح بعد الترحيل
