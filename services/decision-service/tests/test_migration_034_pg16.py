"""Disposable PG16 proof for migration 034 policy composition.

Separate from the application suite to preserve its domain evidence attribution.
"""

from dataclasses import replace

import asyncpg
import migration_runner as runner
import pytest
from test_migration_033_pg16 import (
    COMPOSITION_VERSION,
    HARDENING_VERSIONS,
    LATER_VERSIONS,
    OTHER,
    TABLES,
    TENANT,
    VERSION,
    _insert,
)
from test_migration_033_pg16 import database as database


@pytest.mark.asyncio
@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("owns_table", [False, True], ids=["nonowner", "forced-owner"])
async def test_034_closes_legacy_policy_union(database, monkeypatch, table, owns_table):
    """Reproduce the live v122 permissive policy before exercising the AND guard."""
    await database.admin.execute(
        f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
        "USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')) "
        "WITH CHECK (tenant_id::text = COALESCE("
        "NULLIF(current_setting('app.current_tenant', true), ''), "
        "NULLIF(current_setting('app.tenant_id', true), '')))"
    )
    migrations = runner.load_migrations()
    with monkeypatch.context() as scoped:
        scoped.setattr(
            runner, "load_migrations", lambda: [m for m in migrations if m.version <= VERSION]
        )
        assert (await runner.apply_migrations())["applied_now"] == [VERSION]
    app = await database.app_connection()
    try:
        # Red witness: 033 alone accepts legacy-only context on the live topology.
        tx = app.transaction()
        await tx.start()
        try:
            await app.execute("SELECT set_config('app.tenant_id',$1,true)", TENANT)
            await _insert(app, table, "ci-legacy-before-034", TENANT)
        finally:
            await tx.rollback()

        assert (await runner.apply_migrations())["applied_now"] == [
            COMPOSITION_VERSION,
            *LATER_VERSIONS,
        ]
        if owns_table:
            await database.admin.execute(f'ALTER TABLE {table} OWNER TO "{database.role}"')
        assert (
            await database.admin.fetchval(
                "SELECT permissive FROM pg_policies WHERE tablename=$1 AND policyname=$2",
                table,
                f"{table}_tenant_boundary_guard",
            )
            == "RESTRICTIVE"
        )
        tx = app.transaction()
        await tx.start()
        try:
            await app.execute("SELECT set_config('app.tenant_id',$1,true)", TENANT)
            await app.execute("SELECT set_config('app.current_tenant','',true)")
            with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
                async with app.transaction():
                    await _insert(app, table, "ci-legacy-after-034", TENANT)
            # Canonical context wins even when the legacy key names another tenant.
            await app.execute("SELECT set_config('app.current_tenant',$1,true)", TENANT)
            await app.execute("SELECT set_config('app.tenant_id',$1,true)", OTHER)
            await _insert(app, table, "ci-own-after-034", TENANT)
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 1
            with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
                async with app.transaction():
                    await _insert(app, table, "ci-cross-after-034", OTHER)
            await app.execute("SELECT set_config('app.current_tenant',$1,true)", OTHER)
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 0
            await app.execute("SELECT set_config('app.current_tenant','',true)")
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 0
        finally:
            await tx.rollback()
        assert await database.admin.fetchval(f"SELECT count(*) FROM {table}") == 0
    finally:
        await app.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_033", [False, True], ids=["combined", "033-already-applied"])
async def test_034_failure_restores_policies_and_journal(database, monkeypatch, prior_033):
    """Fail after 034 DDL, with and without an already committed 033."""
    for table in TABLES:
        await database.admin.execute(
            f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
            "USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')) "
            "WITH CHECK (tenant_id::text = COALESCE("
            "NULLIF(current_setting('app.current_tenant', true), ''), "
            "NULLIF(current_setting('app.tenant_id', true), '')))"
        )
    migrations = runner.load_migrations()
    if prior_033:
        with monkeypatch.context() as scoped:
            scoped.setattr(
                runner, "load_migrations", lambda: [m for m in migrations if m.version <= VERSION]
            )
            assert (await runner.apply_migrations())["applied_now"] == [VERSION]

    async def snapshot():
        policies = await database.admin.fetch(
            "SELECT tablename, policyname, permissive, roles, cmd, qual, with_check "
            "FROM pg_policies WHERE schemaname='public' AND tablename=ANY($1::text[]) "
            "ORDER BY tablename, policyname",
            list(TABLES),
        )
        flags = await database.admin.fetch(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relnamespace='public'::regnamespace AND relname=ANY($1::text[]) "
            "ORDER BY relname",
            list(TABLES),
        )
        journal = await database.admin.fetch(
            f"SELECT version, checksum, applied_at FROM {runner.MIGRATION_TABLE} ORDER BY version"
        )
        return policies, flags, journal

    before = await snapshot()
    target = next(m for m in migrations if m.version == COMPOSITION_VERSION)
    broken = replace(target, sql=target.sql + "\nSELECT 1 / 0;")
    with monkeypatch.context() as scoped:
        scoped.setattr(
            runner, "load_migrations", lambda: [broken if m == target else m for m in migrations]
        )
        with pytest.raises(asyncpg.DivisionByZeroError):
            await runner.apply_migrations()
    assert await snapshot() == before, "034 failure must restore policies, RLS flags and journal"
    pending = ([COMPOSITION_VERSION] if prior_033 else HARDENING_VERSIONS) + LATER_VERSIONS
    status = await runner.check_migrations()
    assert status["pending"] == pending and status["checksum_mismatches"] == []
    assert (await runner.apply_migrations())["applied_now"] == pending
    assert (await runner.apply_migrations())["applied_now"] == []
    for table in TABLES:
        assert (
            await database.admin.fetchval(
                "SELECT permissive FROM pg_policies WHERE schemaname='public' "
                "AND tablename=$1 AND policyname=$2",
                table,
                f"{table}_tenant_boundary_guard",
            )
            == "RESTRICTIVE"
        )
