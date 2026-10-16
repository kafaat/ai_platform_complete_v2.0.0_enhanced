"""Disposable PG16 proof for migration 034 policy composition.

Separate from the application suite to preserve its domain evidence attribution.
"""

import asyncio
import hashlib
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

        # Keep this legacy-policy red/green witness on the 034 schema. A later
        # correlation-parent trigger would reject the minimal fixture before
        # reaching RLS. Full application and 036 tests retain the latest schema.
        with monkeypatch.context() as scoped:
            scoped.setattr(
                runner,
                "load_migrations",
                lambda: [m for m in migrations if m.version <= COMPOSITION_VERSION],
            )
            assert (await runner.apply_migrations())["applied_now"] == [COMPOSITION_VERSION]
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


async def _apply_through_033(monkeypatch):
    migrations = runner.load_migrations()
    with monkeypatch.context() as scoped:
        scoped.setattr(
            runner, "load_migrations", lambda: [m for m in migrations if m.version <= VERSION]
        )
        await runner.apply_migrations()
    return next(m for m in migrations if m.version == COMPOSITION_VERSION)


@pytest.mark.asyncio
async def test_scoped_034_applies_only_reviewed_version_and_serializes(database, monkeypatch):
    target = await _apply_through_033(monkeypatch)
    first, second = await asyncio.gather(
        runner.apply_composition_only(target.checksum),
        runner.apply_composition_only(target.checksum),
    )
    assert sorted(len(r["applied_now"]) for r in [first, second]) == [0, 1]
    for result in [first, second]:
        assert result["scope"] == COMPOSITION_VERSION
        assert result["remaining_pending"] == LATER_VERSIONS
        assert not result["staging_acceptance_proven"]
    assert (await runner.check_migrations())["pending"] == LATER_VERSIONS
    assert (
        await database.admin.fetchval(
            f"SELECT count(*) FROM {runner.MIGRATION_TABLE} WHERE version=$1", COMPOSITION_VERSION
        )
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["prior_pending", "prior_checksum", "later_checksum", "unknown"])
async def test_scoped_034_refuses_unreviewed_journal(database, monkeypatch, fault):
    target = await _apply_through_033(monkeypatch)
    if fault == "prior_pending":
        await database.admin.execute(
            f"DELETE FROM {runner.MIGRATION_TABLE} WHERE version=$1", VERSION
        )
    elif fault == "prior_checksum":
        await database.admin.execute(
            f"UPDATE {runner.MIGRATION_TABLE} SET checksum='altered' WHERE version=$1", VERSION
        )
    else:
        version = LATER_VERSIONS[0] if fault == "later_checksum" else "999_unknown.sql"
        await database.admin.execute(
            f"INSERT INTO {runner.MIGRATION_TABLE}(version, checksum) VALUES ($1,'altered')",
            version,
        )
    before = await database.admin.fetch(f"SELECT * FROM {runner.MIGRATION_TABLE} ORDER BY version")
    with pytest.raises(RuntimeError):
        await runner.apply_composition_only(target.checksum)
    assert (
        await database.admin.fetch(f"SELECT * FROM {runner.MIGRATION_TABLE} ORDER BY version")
        == before
    )
    assert (
        await database.admin.fetchval(
            "SELECT count(*) FROM pg_policies WHERE policyname LIKE '%tenant_boundary_guard'"
        )
        == 0
    )


@pytest.mark.asyncio
async def test_scoped_034_failure_rolls_back_policy_and_journal(database, monkeypatch):
    target = await _apply_through_033(monkeypatch)
    sql = target.sql + "\nSELECT 1 / 0;"
    broken = replace(target, sql=sql, checksum=hashlib.sha256(sql.encode()).hexdigest())
    migrations = runner.load_migrations()
    monkeypatch.setattr(
        runner, "load_migrations", lambda: [broken if m == target else m for m in migrations]
    )
    with pytest.raises(asyncpg.DivisionByZeroError):
        await runner.apply_composition_only(broken.checksum)
    assert (
        await database.admin.fetchval(
            "SELECT count(*) FROM pg_policies WHERE policyname LIKE '%tenant_boundary_guard'"
        )
        == 0
    )
    assert not await database.admin.fetchval(
        f"SELECT EXISTS(SELECT 1 FROM {runner.MIGRATION_TABLE} WHERE version=$1)",
        COMPOSITION_VERSION,
    )


@pytest.mark.asyncio
async def test_scoped_034_inspection_is_readonly_and_reports_real_metadata(database, monkeypatch):
    target = await _apply_through_033(monkeypatch)
    before = await database.admin.fetch(f"SELECT * FROM {runner.MIGRATION_TABLE} ORDER BY version")
    result = await runner.inspect_composition()
    assert result["ok"] and result["transaction_read_only"] == "on"
    assert result["source_checksum"] == target.checksum
    assert result["pending"] == [COMPOSITION_VERSION, *LATER_VERSIONS]
    assert result["authorization_or_acceptance"] is False
    assert len(result["tables"]) == 2
    assert all(row["relforcerowsecurity"] for row in result["tables"])
    assert (
        await database.admin.fetch(f"SELECT * FROM {runner.MIGRATION_TABLE} ORDER BY version")
        == before
    )


@pytest.mark.asyncio
async def test_scoped_034_inspection_never_creates_a_missing_journal(database):
    await database.admin.execute(f"DROP TABLE {runner.MIGRATION_TABLE}")
    result = await runner.inspect_composition()
    assert not result["ok"] and result["journal"] == {}
    assert not await runner.migration_table_exists(database.admin)


@pytest.mark.asyncio
async def test_scoped_034_rechecks_force_rls_before_applying(database, monkeypatch):
    target = await _apply_through_033(monkeypatch)
    await database.admin.execute("ALTER TABLE decision_reviews NO FORCE ROW LEVEL SECURITY")
    with pytest.raises(RuntimeError, match="FORCE RLS"):
        await runner.apply_composition_only(target.checksum)
    assert not await database.admin.fetchval(
        f"SELECT EXISTS(SELECT 1 FROM {runner.MIGRATION_TABLE} WHERE version=$1)",
        COMPOSITION_VERSION,
    )


def _pair_hashes():
    known = {m.version: m.checksum for m in runner.load_migrations()}
    return known[VERSION], known[COMPOSITION_VERSION]


@pytest.mark.asyncio
async def test_scoped_pair_from_032_serializes_and_leaves_every_later_migration_pending(database):
    before = await runner.inspect_composition()
    assert not before["ok"] and before["pair_prerequisites_ok"]
    assert set(before["pair_source_checksums"]) == set(HARDENING_VERSIONS)
    first, second = await asyncio.gather(
        runner.apply_hardening_pair(*_pair_hashes()), runner.apply_hardening_pair(*_pair_hashes())
    )
    assert sorted(len(r["applied_now"]) for r in [first, second]) == [0, 2]
    for result in [first, second]:
        assert result["scope"] == "033+034"
        assert result["remaining_pending"] == LATER_VERSIONS
        assert set(result["source_checksums"]) == set(HARDENING_VERSIONS)
    assert (await runner.check_migrations())["pending"] == LATER_VERSIONS


@pytest.mark.asyncio
async def test_scoped_pair_with_033_already_committed_only_applies_034(database, monkeypatch):
    await _apply_through_033(monkeypatch)
    result = await runner.apply_hardening_pair(*_pair_hashes())
    assert result["applied_now"] == [COMPOSITION_VERSION]
    assert result["remaining_pending"] == LATER_VERSIONS


@pytest.mark.asyncio
async def test_scoped_pair_034_error_rolls_back_both_versions_flags_and_journal(
    database, monkeypatch
):
    migrations = runner.load_migrations()
    target = next(m for m in migrations if m.version == COMPOSITION_VERSION)
    sql = target.sql + "\nSELECT 1 / 0;"
    broken = replace(target, sql=sql, checksum=hashlib.sha256(sql.encode()).hexdigest())
    monkeypatch.setattr(
        runner, "load_migrations", lambda: [broken if m == target else m for m in migrations]
    )
    before = await database.admin.fetch(f"SELECT * FROM {runner.MIGRATION_TABLE} ORDER BY version")
    with pytest.raises(asyncpg.DivisionByZeroError):
        await runner.apply_hardening_pair(*_pair_hashes())
    assert (
        await database.admin.fetch(f"SELECT * FROM {runner.MIGRATION_TABLE} ORDER BY version")
        == before
    )
    for table in TABLES:
        assert not await database.admin.fetchval(
            "SELECT relrowsecurity OR relforcerowsecurity FROM pg_class WHERE oid=$1::regclass",
            table,
        )
        assert (
            await database.admin.fetchval(
                "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename=$1", table
            )
            == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("table", TABLES)
async def test_scoped_pair_preserves_canonical_boundary_on_live_legacy_policy_topology(
    database, table
):
    await database.admin.execute(
        f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
        "USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')) "
        "WITH CHECK (tenant_id::text = COALESCE(NULLIF(current_setting('app.current_tenant', true), ''), NULLIF(current_setting('app.tenant_id', true), '')))"
    )
    assert (await runner.apply_hardening_pair(*_pair_hashes()))["applied_now"] == HARDENING_VERSIONS
    app = await database.app_connection()
    try:
        tx = app.transaction()
        await tx.start()
        try:
            await app.execute("SELECT set_config('app.tenant_id',$1,true)", TENANT)
            for canonical in ["", OTHER]:
                await app.execute("SELECT set_config('app.current_tenant',$1,true)", canonical)
                with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
                    async with app.transaction():
                        await _insert(app, table, "pair-rejected", TENANT)
            await app.execute("SELECT set_config('app.current_tenant',$1,true)", TENANT)
            await app.execute("SELECT set_config('app.tenant_id',$1,true)", OTHER)
            await _insert(app, table, "pair-own", TENANT)
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 1
            await app.execute("SELECT set_config('app.tenant_id','',true)")
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 1
            await _insert(app, table, "pair-canonical-only", TENANT)
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 2
            await app.execute("SELECT set_config('app.current_tenant','',true)")
            await app.execute("SELECT set_config('app.tenant_id','',true)")
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 0
            with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
                async with app.transaction():
                    await _insert(app, table, "pair-missing", TENANT)
        finally:
            await tx.rollback()
        assert await database.admin.fetchval(f"SELECT count(*) FROM {table}") == 0
    finally:
        await app.close()
