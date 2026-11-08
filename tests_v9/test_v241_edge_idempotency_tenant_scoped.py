"""v241 / CP997-05 — edge idempotency is unique per tenant, not globally.

Static half (unit): the migration installs the tenant-scoped index before dropping the global
one, and the router's ON CONFLICT target names exactly that index's columns. A target that no
unique index matches makes every insert fail, so the two must move together.

Live half (integration, needs TEST_DATABASE_ADMIN_URL on a database built from MANIFEST): a key
already used by tenant A no longer blocks tenant B, while the same tenant's replay still hits the
conflict and inserts nothing.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "v241_edge_idempotency_tenant_scoped.sql"
ROUTER = ROOT / "services" / "sahool-platform" / "api" / "routers" / "edge.py"


@pytest.mark.unit
def test_migration_creates_the_tenant_index_before_dropping_the_global_one():
    sql = MIGRATION.read_text(encoding="utf-8")
    create = sql.index("CREATE UNIQUE INDEX IF NOT EXISTS uq_edge_idempotency_tenant")
    drop = sql.index("DROP INDEX IF EXISTS uq_edge_idempotency;")
    rename = sql.index("ALTER INDEX uq_edge_idempotency_tenant RENAME TO uq_edge_idempotency;")
    assert create < drop < rename
    assert "ON edge_results (tenant_id, idempotency_key)" in sql
    assert "WHERE idempotency_key IS NOT NULL" in sql


@pytest.mark.unit
def test_the_tenant_index_keeps_v9s_name_so_a_manifest_replay_cannot_recreate_the_global_one():
    """Copilot on #1342: the migrator replays MANIFEST, so v9 runs again before v241.

    v9's ``CREATE UNIQUE INDEX IF NOT EXISTS uq_edge_idempotency`` is a no-op only if that
    name is already taken by the converted index; under any other name it rebuilds the global
    index and fails once two tenants share a key.
    """
    v9 = (ROOT / "migrations" / "v9_edge_idempotency.sql").read_text(encoding="utf-8")
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_edge_idempotency\n" in v9
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "IF v_cols = 2 THEN" in sql, "the conversion must be idempotent on replay"


@pytest.mark.unit
def test_router_conflict_target_matches_the_tenant_index():
    src = ROUTER.read_text(encoding="utf-8")
    assert "ON CONFLICT (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL" in src
    assert "ON CONFLICT (idempotency_key)" not in src, (
        "a global conflict target lets one tenant's key collide with another's (CP997-05)"
    )


@pytest.mark.unit
def test_migration_is_registered_before_v206_in_both_runners():
    manifest = [
        line.strip()
        for line in (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert manifest[-1] == "v206_rls_final_hardening.sql"
    assert "v241_edge_idempotency_tenant_scoped.sql" in manifest[:-1]
    runner = (ROOT / "scripts_v9" / "run_migrations.sql").read_text(encoding="utf-8")
    assert runner.index("v241_edge_idempotency_tenant_scoped.sql") < runner.index(
        "\\i migrations/v206_rls_final_hardening.sql"
    )


_ADMIN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""


@pytest.mark.integration
@pytest.mark.skipif(not _ADMIN, reason="needs TEST_DATABASE_ADMIN_URL on a migrated database")
def test_a_key_used_by_one_tenant_no_longer_blocks_another():
    asyncpg = pytest.importorskip("asyncpg")
    import asyncio

    async def run():
        conn = await asyncpg.connect(_ADMIN)
        field = f"v241-{uuid.uuid4().hex[:8]}"
        key = uuid.uuid4().hex
        tenants = [str(uuid.uuid4()), str(uuid.uuid4())]
        insert = (
            "INSERT INTO edge_results (field_id, tenant_id, result_type, result_data,"
            " idempotency_key) VALUES ($1, $2::uuid, 'pest', '{}'::jsonb, $3)"
            " ON CONFLICT (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
            " DO NOTHING RETURNING id"
        )
        try:
            # edge_results.field_id references field_boundaries (v9).
            await conn.execute(
                "INSERT INTO field_boundaries (field_id, field_name) VALUES ($1, 'v241')", field
            )
            first = await conn.fetchval(insert, field, tenants[0], key)
            other_tenant = await conn.fetchval(insert, field, tenants[1], key)
            replay = await conn.fetchval(insert, field, tenants[0], key)
            assert first is not None, "the first insert must store a row"
            assert other_tenant is not None, "tenant B was blocked by tenant A's key (CP997-05)"
            assert replay is None, "a same-tenant replay must hit the conflict, not insert"
            count = await conn.fetchval(
                "SELECT count(*) FROM edge_results WHERE idempotency_key = $1", key
            )
            assert count == 2
            idx_cols = (
                "SELECT i.indnatts FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid"
                " WHERE c.relname = 'uq_edge_idempotency'"
            )
            assert await conn.fetchval(idx_cols) == 2, (
                "uq_edge_idempotency must be the tenant-scoped (two-column) index"
            )
            assert (
                await conn.fetchval("SELECT to_regclass('public.uq_edge_idempotency_tenant')")
                is None
            )
            # Copilot on #1342: replay v9 then v241, as the migrator does on every run, with the
            # cross-tenant duplicate in place. Before the fix v9 rebuilt the global index here.
            for name in ("v9_edge_idempotency.sql", "v241_edge_idempotency_tenant_scoped.sql"):
                await conn.execute((ROOT / "migrations" / name).read_text(encoding="utf-8"))
            assert await conn.fetchval(idx_cols) == 2, (
                "a manifest replay re-created the global index"
            )
        finally:
            await conn.execute("DELETE FROM edge_results WHERE field_id = $1", field)
            await conn.execute("DELETE FROM field_boundaries WHERE field_id = $1", field)
            await conn.close()

    asyncio.run(run())
