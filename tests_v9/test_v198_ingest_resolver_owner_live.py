"""برهان PostgreSQL حيّ لـv198 (SCOUT-INGEST-01 / B1.2b) — مالك resolver (FORCE ↔ DEFINER).

يُثبت الحسم المانع: SECURITY DEFINER + FORCE RLS ⇒ المالك يجب أن يكون BYPASSRLS، وإلّا تُجوَّع
الدالّة (صفر صفوف بسياق فارغ = كلّ توكن 403 = سطح ميت). يعمل تحت ``-m integration`` فقط،
يتخطّى بلا قاعدة. مُصادَق حيّاً على PG16 أصليّ (جلسة 2026-07-19).
"""

from __future__ import annotations

import os
import uuid

import pytest

asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")
pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@localhost:5433/sahool_test"
)
TABLE = "eis_owner_test"
FN = "resolve_eis_owner_test"
RESOLVER = "eis_resolver_test"  # NOSUPERUSER BYPASSRLS
BADOWNER = "eis_badowner_test"  # NOSUPERUSER NOBYPASSRLS
APP = "eis_app_test"  # NOSUPERUSER NOBYPASSRLS
_HASH = "a" * 64


@pytest.fixture
async def db():
    try:
        conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}")
    try:
        for role, extra in (
            (RESOLVER, "BYPASSRLS"),
            (BADOWNER, "NOBYPASSRLS"),
            (APP, "NOBYPASSRLS"),
        ):
            await conn.execute(f"""
                DO $$ BEGIN
                  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                    CREATE ROLE {role} NOLOGIN NOSUPERUSER NOINHERIT {extra};
                  END IF;
                END $$;""")
        await conn.execute(f"DROP TABLE IF EXISTS {TABLE} CASCADE")
        await conn.execute(f"""
            CREATE TABLE {TABLE} (
              tenant_id UUID NOT NULL, token_hash TEXT NOT NULL, enabled BOOLEAN NOT NULL DEFAULT true)""")
        await conn.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
        await conn.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
        await conn.execute(
            f"CREATE POLICY tenant_isolation ON {TABLE} "
            "USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))"
        )
        await conn.execute(f"""
            CREATE OR REPLACE FUNCTION {FN}(p TEXT) RETURNS TABLE(tenant_id UUID)
            LANGUAGE sql SECURITY DEFINER SET search_path=public AS $$
              SELECT t.tenant_id FROM {TABLE} t WHERE t.token_hash=p AND t.enabled=true LIMIT 1; $$""")
        for role in (RESOLVER, BADOWNER, APP):
            await conn.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            await conn.execute(f"GRANT SELECT ON {TABLE} TO {role}")
            await conn.execute(f"GRANT EXECUTE ON FUNCTION {FN}(TEXT) TO {role}")
        tid = uuid.uuid4()
        await conn.execute(
            f"INSERT INTO {TABLE}(tenant_id, token_hash) VALUES ($1, '{_HASH}')", tid
        )
        yield conn, tid
    finally:
        await conn.execute(f"DROP TABLE IF EXISTS {TABLE} CASCADE")
        await conn.close()


async def test_bypassrls_owner_resolves_with_empty_context(db) -> None:
    """CASE 1: مالك BYPASSRLS ⇒ الدالّة تحلّ التوكن رغم سياق فارغ (غرضها)."""
    conn, tid = db
    await conn.execute(f"ALTER FUNCTION {FN}(TEXT) OWNER TO {RESOLVER}")
    await conn.execute(f"SET ROLE {APP}")
    await conn.execute("SELECT set_config('app.current_tenant','',false)")
    got = await conn.fetchval(f"SELECT tenant_id FROM {FN}('{_HASH}')")
    await conn.execute("RESET ROLE")
    assert got == tid


async def test_nonbypass_owner_starves_under_force(db) -> None:
    """CASE 2: مالك خاضع لـFORCE ⇒ صفر صفوف = الفخّ الذي رصدته المراجعة (سطح ميت لو اعتُمد)."""
    conn, _tid = db
    await conn.execute(f"ALTER FUNCTION {FN}(TEXT) OWNER TO {BADOWNER}")
    await conn.execute(f"SET ROLE {APP}")
    await conn.execute("SELECT set_config('app.current_tenant','',false)")
    count = await conn.fetchval(f"SELECT count(*) FROM {FN}('{_HASH}')")
    await conn.execute("RESET ROLE")
    assert count == 0
