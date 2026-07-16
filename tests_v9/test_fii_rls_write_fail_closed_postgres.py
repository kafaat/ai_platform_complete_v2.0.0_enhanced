"""Live PostgreSQL proof for FII Safety Increment 1B.

Runs only under ``pytest -m integration`` and skips when TEST_DATABASE_URL is unavailable.
The fixture creates isolated test tables with the exact v192 policy so it does not depend
on the full migration chain being present in a developer database.
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
ROLE = "fii_rls_app_test"
TABLES = ("fii_rls_scouting_test", "fii_rls_prescriptions_test")


@pytest.fixture
async def db():
    try:
        conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}")
    try:
        await conn.execute(f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOSUPERUSER NOBYPASSRLS NOINHERIT;
              END IF;
            END $$;
        """)
        for table in TABLES:
            await conn.execute(f"DROP TABLE IF EXISTS {table}")
            await conn.execute(
                f"CREATE TABLE {table} (id text primary key, tenant_id uuid not null)"
            )
            await conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            await conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            await conn.execute(f"""
                CREATE POLICY tenant_isolation ON {table}
                USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
                WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
            """)
            await conn.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {ROLE}")
        yield conn
    finally:
        await conn.execute("RESET ROLE")
        await conn.execute("SELECT set_config('app.current_tenant', '', false)")
        for table in TABLES:
            await conn.execute(f"DROP TABLE IF EXISTS {table}")
        await conn.close()


async def _set_role(conn):
    await conn.execute(f"SET ROLE {ROLE}")


@pytest.mark.parametrize("table", TABLES)
async def test_missing_empty_malformed_wrong_context_cannot_insert(db, table):
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    await _set_role(db)
    for context in (None, "", "not-a-uuid", tenant_b):
        await db.execute("SELECT set_config('app.current_tenant', $1, false)", context or "")
        with pytest.raises(asyncpg.PostgresError):
            await db.execute(
                f"INSERT INTO {table} (id, tenant_id) VALUES ($1, $2::uuid)",
                uuid.uuid4().hex,
                tenant_a,
            )
    await db.execute("RESET ROLE")


@pytest.mark.parametrize("table", TABLES)
async def test_correct_context_allows_only_matching_tenant(db, table):
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    await _set_role(db)
    await db.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)
    row_id = uuid.uuid4().hex
    await db.execute(f"INSERT INTO {table} (id, tenant_id) VALUES ($1, $2::uuid)", row_id, tenant_a)
    assert await db.fetchval(f"SELECT count(*) FROM {table}") == 1
    with pytest.raises(asyncpg.PostgresError):
        await db.execute(
            f"INSERT INTO {table} (id, tenant_id) VALUES ($1, $2::uuid)", uuid.uuid4().hex, tenant_b
        )
    await db.execute("RESET ROLE")


@pytest.mark.parametrize("table", TABLES)
async def test_pool_context_reset_prevents_tenant_leak(db, table):
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    await _set_role(db)
    await db.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)
    await db.execute(
        f"INSERT INTO {table} (id, tenant_id) VALUES ($1, $2::uuid)", uuid.uuid4().hex, tenant_a
    )
    await db.execute("SELECT set_config('app.current_tenant', '', false)")
    assert await db.fetchval(f"SELECT count(*) FROM {table}") == 0
    await db.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_b)
    assert await db.fetchval(f"SELECT count(*) FROM {table}") == 0
    await db.execute("RESET ROLE")
