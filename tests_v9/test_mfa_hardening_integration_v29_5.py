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
    sys.path.insert(0, os.path.join(ROOT, "services/auth"))
    sys.path.insert(0, ROOT)
    spec = importlib.util.spec_from_file_location(
        "auth_main_mfa", os.path.join(ROOT, "services/auth/main.py")
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["auth_main_mfa"] = m
    spec.loader.exec_module(m)
    return m


@pytest.mark.integration
@pytest.mark.xfail(
    strict=False,
    reason=(
        "CI-RLS-SUPERUSER-ROLE-01: خدمة auth ترفض الإقلاع لأنّ قاعدة اختبار CI تتّصل "
        "بـsahool_test وهو superuser، وحارس تجاوز RLS يفشل مغلقاً — وهو سلوك صحيح. "
        "ci.yml:626 يُقرّ بالدور صراحةً. الإصلاح دور مقيَّد لقاعدة الاختبار، لا "
        "SAHOOL_ALLOW_RLS_BYPASS_ROLE=1 (يُعطّل الحارس في CI)."
    ),
)
def test_mfa_end_to_end_via_app():
    pytest.importorskip("fastapi")  # DB-only CI job has no fastapi ⇒ skip transparently there
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
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
            "/auth/register",
            json={"email": email, "password": pw, "full_name": "مزارع MFA", "role": "owner"},
        ).json()["access_token"]
        auth = {"Authorization": f"Bearer {tok}"}
        r = c.post("/auth/mfa/setup", headers=auth)
        assert r.status_code == 200, r.text[:160]
        secret = r.json()["secret"]
        row = asyncio.run(
            _fetchrow("SELECT mfa_secret, encrypted_mfa_secret FROM users WHERE email=$1", email)
        )
        assert row["encrypted_mfa_secret"] and str(row["encrypted_mfa_secret"]).startswith("v1:")
        assert row["mfa_secret"] is None  # never new plaintext
        r = c.post("/auth/mfa/activate", headers=auth, json={"code": pyotp.TOTP(secret).now()})
        assert r.status_code == 200 and len(r.json()["recovery_codes"]) == 10
        r = c.post(
            "/auth/login",
            json={"email": email, "password": pw, "mfa_code": pyotp.TOTP(secret).now()},
        )
        assert r.status_code == 200, r.text[:160]
