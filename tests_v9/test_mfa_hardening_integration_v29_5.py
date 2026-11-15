"""تحقّق تكامل V29.5/V29.6 — تصلّب MFA على Postgres حقيقيّ (مثل بقيّة اختبارات integration).

مهمّ (تصحيح): وظيفة CI *Integration* تضبط ``TEST_DATABASE_URL`` (لا ``DATABASE_URL``) وهي
**طبقة قاعدة بيانات بلا fastapi**. لذا:
- ``test_mfa_migrations_applied_on_real_postgres`` (asyncpg نقيّ) — **يعمل في CI**: يثبت أنّ v128+v129
  طُبِّقا فعلاً (أعمدة/جداول/قيود/سياسات RLS المُضيَّقة/trigger append-only)، وأنّ append-only يمنع
  التعديل سلوكيّاً (probe داخل transaction يُلغى فلا يلوّث).
- ``test_mfa_end_to_end_via_app`` (TestClient) — يتطلّب fastapi + DB؛ يعمل محليّاً ويتخطّى بوضوح
  حيث لا fastapi (لا تخطٍّ صامت خاطئ).

يعمل بـ``pytest -m integration`` — يتخطّى إن لا Postgres.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import time
import uuid

import pytest

pytestmark = pytest.mark.integration

_TEST_DB = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _db_available() -> bool:
    try:
        import asyncpg

        async def _ping():
            c = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
            await c.close()

        asyncio.run(_ping())
        return True
    except Exception:
        return False


# ── DB-contract verification (runs in the CI Integration job — pure asyncpg) ──
@pytest.mark.integration
def test_mfa_migrations_applied_on_real_postgres():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import asyncpg

    async def _check():
        conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
        try:
            # service context (auth pool sets this) — required by the tightened v129 RLS.
            await conn.execute("SELECT set_config('app.current_role', 'admin', false)")

            # v128 — users hardening columns.
            ucols = {
                r["column_name"]
                for r in await conn.fetch(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='users'"
                )
            }
            for col in (
                "encrypted_mfa_secret",
                "mfa_failed_attempts",
                "mfa_locked_until",
                "mfa_enabled_at",
                "mfa_last_verified_at",
            ):
                assert col in ucols, f"عمود users مفقود بعد v128: {col}"

            # v128 — tables + recovery unique(one-time) index.
            tables = {
                r["table_name"]
                for r in await conn.fetch(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name IN ('mfa_recovery_codes','mfa_audit_events')"
                )
            }
            assert {"mfa_recovery_codes", "mfa_audit_events"} <= tables
            idx = {
                r["indexname"]
                for r in await conn.fetch(
                    "SELECT indexname FROM pg_indexes WHERE tablename='mfa_recovery_codes'"
                )
            }
            assert "uq_mfa_recovery_codes_user_hash" in idx

            # v129 — tightened RLS: recovery is service-only (role='admin'), NO self-read.
            pol = {
                r["policyname"]: (r["qual"] or "")
                for r in await conn.fetch(
                    "SELECT policyname, qual FROM pg_policies WHERE tablename='mfa_recovery_codes'"
                )
            }
            rec_qual = pol.get("mfa_recovery_codes_policy", "")
            assert "current_role" in rec_qual and "'admin'" in rec_qual  # service-only escape
            assert "current_user_id" not in rec_qual  # no self-read of code hashes

            # v129 — audit policy keeps the role='admin' service escape (no bare tenant-null).
            aud = {
                r["policyname"]: (r["qual"] or "")
                for r in await conn.fetch(
                    "SELECT policyname, qual FROM pg_policies WHERE tablename='mfa_audit_events'"
                )
            }
            aud_qual = aud.get("mfa_audit_events_policy", "")
            assert "current_role" in aud_qual and "'admin'" in aud_qual

            # v129 — mfa_audit_events is append-only (trigger present + behaviourally enforced).
            trg = {
                r["tgname"]
                for r in await conn.fetch(
                    "SELECT tgname FROM pg_trigger WHERE tgrelid='mfa_audit_events'::regclass "
                    "AND NOT tgisinternal"
                )
            }
            assert "trg_append_only_mfa_audit_events" in trg
            # behavioural probe inside a transaction that we force to roll back (no pollution):
            # INSERT is allowed, UPDATE must raise (append-only) which aborts+rolls back the tx.
            raised = False
            try:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO mfa_audit_events (user_id, event, outcome) "
                        "VALUES (NULL, 'integration_probe', 'probe')"
                    )
                    await conn.execute(
                        "UPDATE mfa_audit_events SET outcome='x' WHERE event='integration_probe'"
                    )
            except asyncpg.PostgresError:
                raised = True
            assert raised, "append-only trigger لم يمنع UPDATE على mfa_audit_events"
        finally:
            await conn.close()

    asyncio.run(_check())


# ── full app flow (TestClient) — runs where fastapi+DB exist; skips transparently otherwise ──
def _load_auth_main():
    from tests_v9.service_module import purge_generic_modules

    auth_dir = os.path.join(ROOT, "services/auth")
    for p in (ROOT, auth_dir):
        while p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, ROOT)
    sys.path.insert(0, auth_dir)  # auth أوّلاً: routers/router_registry تُحلّ من الخدمة نفسها
    purge_generic_modules()
    spec = importlib.util.spec_from_file_location(
        "auth_main_mfa", os.path.join(ROOT, "services/auth/main.py")
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["auth_main_mfa"] = m
    # تدقيق 2026-11-01 (Q5): الراوترات تستورد ``main`` باسمه؛ بلا هذا الربط تُحمَّل نسخةٌ
    # ثانية ``_pool`` فيها None ⇒ register=500 — العطلُ نفسُه الذي أُصلِح في test_auth_e2e
    # (9a3ce99). كان ``xfail(strict=False)`` يبتلعه حتى تحت الدور المقيَّد.
    sys.modules["main"] = m
    spec.loader.exec_module(m)
    return m


# MFA_E2E_CERTIFICATION_REQUIRED=1 (خطوة CI المخصَّصة بالدور المقيَّد): كلّ تخطٍّ فشلٌ.
_CERTIFICATION_REQUIRED = os.getenv("MFA_E2E_CERTIFICATION_REQUIRED") == "1"


def _skip_or_fail(message: str) -> None:
    if _CERTIFICATION_REQUIRED:
        pytest.fail(message)
    pytest.skip(message)


def _role_bypasses_rls() -> bool:
    """دورُ الاتّصال superuser أو BYPASSRLS؟ — حارس auth يرفض الإقلاع عليه بحقّ."""
    import asyncpg

    async def _q():
        conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
        try:
            return await conn.fetchval(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
        finally:
            await conn.close()

    return bool(asyncio.run(_q()))


# كان هنا ``xfail(strict=False)`` باسم AUTH-E2E-UNDER-RESTRICTED-ROLE (مُغلَقة 2026-07-18):
# تحت الدور المقيَّد كان الاختبار يفشل بعطل المُحمِّل أعلاه، فيُقرأ «xfailed» أخضر — أيّ
# انحدارٍ حقيقيّ في MFA كان سيُقرأ كذلك. صار يُشغَّل فعلاً في خطوة CI مخصَّصة بالدور
# المقيَّد ``sahool_app_test``؛ وفي الجولة العامّة (superuser) يتخطّى مُعلِناً لأنّ حارس
# auth يرفض الإقلاع على دورٍ يتجاوز RLS — وهو السلوك الصحيح لا العيب.
@pytest.mark.integration
def test_mfa_end_to_end_via_app():
    try:
        import fastapi  # noqa: F401
    except ImportError:
        _skip_or_fail("fastapi غير مثبّتة — تطبيق auth لا يُبنى هنا")
    if not _db_available():
        _skip_or_fail("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    if _role_bypasses_rls():
        _skip_or_fail(
            "دور TEST_DATABASE_URL يتجاوز RLS (superuser/BYPASSRLS) ⇒ حارس auth يرفض الإقلاع "
            "بحقّ. شغّله بدورٍ مقيَّد (خطوة CI: MFA end-to-end, restricted role)."
        )
    import asyncpg
    import pyotp
    from fastapi.testclient import TestClient

    os.environ["DATABASE_URL"] = _TEST_DB  # the auth app reads DATABASE_URL
    os.environ.setdefault("REDIS_URL", os.getenv("TEST_REDIS_URL", "redis://localhost:6380/0"))
    os.environ.setdefault("JWT_SECRET", "z" * 48)
    os.environ.setdefault("SAHOOL_ENV", "development")
    os.environ.setdefault("MFA_SECRET_ENCRYPTION_KEY", "integration-mfa-key-" + "x" * 24)

    async def _fetchrow(sql, *args):
        conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
        try:
            await conn.execute("SELECT set_config('app.current_role', 'admin', false)")
            return await conn.fetchrow(sql, *args)
        finally:
            await conn.close()

    m = _load_auth_main()
    pw = "S3cure-Pass!2026"
    email = f"mfa_{uuid.uuid4().hex[:8]}@sahool.ye"
    with TestClient(m.app, raise_server_exceptions=False) as c:
        tok = c.post(
            "/v1/auth/register",
            json={"email": email, "password": pw, "full_name": "مزارع MFA", "role": "owner"},
        ).json()["access_token"]
        auth = {"Authorization": f"Bearer {tok}"}
        r = c.post("/v1/auth/mfa/setup", headers=auth)
        assert r.status_code == 200, r.text[:160]
        secret = r.json()["secret"]
        row = asyncio.run(
            _fetchrow("SELECT mfa_secret, encrypted_mfa_secret FROM users WHERE email=$1", email)
        )
        assert row["encrypted_mfa_secret"] and str(row["encrypted_mfa_secret"]).startswith("v1:")
        assert row["mfa_secret"] is None  # never new plaintext
        totp = pyotp.TOTP(secret)
        activation_code = totp.now()
        r = c.post("/v1/auth/mfa/activate", headers=auth, json={"code": activation_code})
        assert r.status_code == 200 and len(r.json()["recovery_codes"]) == 10
        # V29.7 anti-replay: رمزُ التفعيل استُهلِكت خطوتُه ⇒ إعادتُه للدخول مرفوضة. كان الاختبار
        # يدخل بـ``now()`` نفسه فيُرفَض بحقّ — وذلك ما ابتلعه ``xfail(strict=False)``.
        r = c.post(
            "/v1/auth/login",
            json={"email": email, "password": pw, "mfa_code": activation_code},
        )
        assert r.status_code == 401, r.text[:160]
        # الخطوة التالية داخل نافذة ±1 ولم تُستهلَك بعد ⇒ دخولٌ ناجح.
        r = c.post(
            "/v1/auth/login",
            json={"email": email, "password": pw, "mfa_code": totp.at(int(time.time()) + 30)},
        )
        assert r.status_code == 200, r.text[:160]


# ── AUTH-02: password-proven bootstrap enrollment on the REAL schema (trigger included) ──
# The HTTP suite (tests_v9/test_auth_enrollment_http.py) doubles the DB. This replays the
# real migrations: ``trg_users_updated_at`` (v9_foundation.sql:53) bumps updated_at on the
# anti-replay TOTP-step write and on the failure-counter write that run *inside* activation.
# A proof bound to updated_at returned 409 here on every activation (review 2026-11-11), and
# a single wrong code invalidated it. Runs in the same restricted-role CI step as the e2e
# test above (Integration Tests → "MFA end-to-end via the real auth app (restricted role)").
@pytest.mark.integration
def test_mfa_bootstrap_enrollment_on_real_postgres(monkeypatch):
    try:
        import fastapi  # noqa: F401
    except ImportError:
        _skip_or_fail("fastapi غير مثبّتة — تطبيق auth لا يُبنى هنا")
    if not _db_available():
        _skip_or_fail("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    if _role_bypasses_rls():
        _skip_or_fail(
            "دور TEST_DATABASE_URL يتجاوز RLS (superuser/BYPASSRLS) ⇒ حارس auth يرفض الإقلاع "
            "بحقّ. شغّله بدورٍ مقيَّد (خطوة CI: MFA end-to-end, restricted role)."
        )
    import asyncpg
    import pyotp
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATABASE_URL", _TEST_DB)
    monkeypatch.setenv("REDIS_URL", os.getenv("TEST_REDIS_URL", "redis://localhost:6380/0"))
    monkeypatch.setenv("JWT_SECRET", os.getenv("JWT_SECRET") or "z" * 48)
    monkeypatch.setenv("SAHOOL_ENV", os.getenv("SAHOOL_ENV") or "development")
    monkeypatch.setenv(
        "MFA_SECRET_ENCRYPTION_KEY",
        os.getenv("MFA_SECRET_ENCRYPTION_KEY") or "integration-mfa-key-" + "x" * 24,
    )
    monkeypatch.setenv("ENFORCE_SENSITIVE_MFA", "true")
    monkeypatch.setenv("REQUIRE_MFA_ROLES", "admin")
    monkeypatch.setenv("MFA_SELF_ENROLLMENT_SCOPE", "bootstrap")

    async def _sql(method, sql, *args):
        conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
        try:
            await conn.execute("SELECT set_config('app.current_role', 'admin', false)")
            return await getattr(conn, method)(sql, *args)
        finally:
            await conn.close()

    trigger = asyncio.run(
        _sql(
            "fetchval",
            "SELECT count(*) FROM pg_trigger WHERE tgrelid='users'::regclass "
            "AND tgname='trg_users_updated_at' AND tgenabled <> 'D'",
        )
    )
    assert trigger == 1, "the updated_at trigger this test exists for is not installed"

    m = _load_auth_main()
    pw = "S3cure-Pass!2026"
    tenant = uuid.uuid4()
    first = f"mfa_boot_{uuid.uuid4().hex[:8]}@sahool.ye"
    second = f"mfa_boot_{uuid.uuid4().hex[:8]}@sahool.ye"
    for email in (first, second):
        asyncio.run(
            _sql(
                "execute",
                "INSERT INTO users (email, password_hash, full_name, role, tenant_id) "
                "VALUES ($1, $2, 'bootstrap admin', 'admin', $3)",
                email,
                m.hash_password(pw, 4),
                tenant,
            )
        )

    def _state(email):
        return asyncio.run(
            _sql(
                "fetchrow",
                "SELECT mfa_enabled, mfa_enabled_at, updated_at FROM users WHERE email=$1",
                email,
            )
        )

    with TestClient(m.app, raise_server_exceptions=False) as c:
        r = c.post("/v1/auth/login", json={"email": first, "password": pw})
        assert r.status_code == 403, r.text[:200]
        assert "access_token" not in r.json()
        proof = r.json()["enrollment_token"]
        assert r.json()["expires_in"] == 300

        r = c.post("/v1/auth/mfa/setup", headers={"Authorization": f"Bearer {proof}"})
        assert r.status_code == 200, r.text[:200]
        secret = r.json()["secret"]
        activation = {"Authorization": f"Bearer {r.json()['enrollment_token']}"}
        after_setup = _state(first)["updated_at"]

        totp = pyotp.TOTP(secret)
        valid = {totp.at(time.time() + 30 * k) for k in (-1, 0, 1)}
        wrong = next(f"{n:06d}" for n in range(1000000) if f"{n:06d}" not in valid)
        r = c.post("/v1/auth/mfa/activate", headers=activation, json={"code": wrong})
        assert r.status_code == 400, r.text[:200]
        # the failure counter UPDATE fired the trigger: updated_at moved under the proof
        assert _state(first)["updated_at"] != after_setup

        code = totp.now()
        r = c.post("/v1/auth/mfa/activate", headers=activation, json={"code": code})
        assert r.status_code == 200, r.text[:200]  # was 409 with updated_at in the binding
        assert len(r.json()["recovery_codes"]) == 10
        row = _state(first)
        assert row["mfa_enabled"] is True and row["mfa_enabled_at"] is not None

        r = c.post(
            "/v1/auth/login",
            json={"email": first, "password": pw, "mfa_code": totp.at(int(time.time()) + 30)},
        )
        assert r.status_code == 200, r.text[:200]
        assert r.json()["role"] == "admin"

        # Bootstrap is now closed for this tenant: the second unenrolled admin gets the
        # pre-patch 403 with no enrollment capability (bootstrap SQL measured on real PG).
        r = c.post("/v1/auth/login", json={"email": second, "password": pw})
        assert r.status_code == 403, r.text[:200]
        assert r.headers.get("x-mfa-enrollment-required") == "true"
        assert "enrollment_token" not in r.json()
        assert _state(second)["mfa_enabled"] is False
