"""Disposable PG16 proof, never a staging probe.

Run only against the dedicated loopback CI database below. Each case creates its
own database and LOGIN role, applies the real 001..032 runner, then tests 033.
Application compatibility assertions are deliberately NOT xfailed: a restrictive
policy passing in isolation does not mean existing writers/readers can use it.
"""

from __future__ import annotations

import os
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import migration_runner as runner
import persistence
import pytest
import pytest_asyncio

ADMIN_DSN = "postgresql://decision033_admin:disposable_test_only@127.0.0.1:5436/decision033_test"
TENANT = "00000000-0000-0000-0000-000000000033"
OTHER = "00000000-0000-0000-0000-000000000034"
VERSION = "033_tenant_boundary_hardening.sql"
TABLES = ("decision_outbox_events", "decision_reviews")


def _configured_dsn() -> str:
    value = os.getenv("DECISION_033_TEST_DATABASE_URL", "")
    if not value:
        if os.getenv("DECISION_033_REQUIRE_PG16") == "1":
            pytest.fail("PG16 proof is required; dedicated test database is missing")
        pytest.skip("requires the dedicated disposable PostgreSQL 16 job")
    # An exact allowlist prevents reuse with Railway DSNs, secrets, or arbitrary DBs.
    if value != ADMIN_DSN:
        pytest.fail("refusing a non-disposable/non-loopback database target")
    return value


async def _connect(dsn):
    return await asyncpg.connect(
        dsn,
        statement_cache_size=0,
        timeout=10,
        command_timeout=20,
        server_settings={"lock_timeout": "5s", "statement_timeout": "15s"},
    )


@pytest_asyncio.fixture
async def database(monkeypatch):
    """Admin is used for setup/inspection only; application calls authenticate afresh."""
    root = await _connect(_configured_dsn())
    suffix = uuid4().hex
    dbname, role = f"decision033_{suffix}", f"decision033_app_{suffix}"
    admin = None
    db_created = role_created = False
    try:
        version = int(await root.fetchval("SHOW server_version_num"))
        assert 160000 <= version < 170000, "this witness requires PostgreSQL 16"
        await root.execute(f'CREATE DATABASE "{dbname}"')
        db_created = True
        await root.execute(
            f"CREATE ROLE \"{role}\" LOGIN PASSWORD 'disposable_test_only' "
            "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT"
        )
        role_created = True
        parts = urlsplit(ADMIN_DSN)
        admin_dsn = urlunsplit(parts._replace(path=f"/{dbname}"))
        app_dsn = urlunsplit(
            parts._replace(netloc=f"{role}:disposable_test_only@127.0.0.1:5436", path=f"/{dbname}")
        )
        admin = await _connect(admin_dsn)

        async def admin_connection():
            return await _connect(admin_dsn)

        async def app_connection():
            return await _connect(app_dsn)

        monkeypatch.setattr(runner, "_connect", admin_connection)
        monkeypatch.setattr(persistence, "_connect", app_connection)
        monkeypatch.setenv("DECISION_SERVICE_ALLOW_SCHEMA_CHANGE", "true")
        migrations = runner.load_migrations()
        baseline = [m for m in migrations if m.version < VERSION]
        assert len(baseline) == 32
        with monkeypatch.context() as scoped:
            scoped.setattr(runner, "load_migrations", lambda: baseline)
            assert (await runner.apply_migrations())["ok"]
        await admin.execute(f'GRANT USAGE, CREATE ON SCHEMA public TO "{role}"')
        await admin.execute(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"'
        )
        app = await app_connection()
        try:
            identity = await app.fetchrow(
                "SELECT current_user AS role, session_user AS session, "
                "rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname=current_user"
            )
            assert dict(identity) == {
                "role": role,
                "session": role,
                "rolsuper": False,
                "rolbypassrls": False,
                "rolcanlogin": True,
            }
            assert not await app.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_auth_members "
                "WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user))"
            )
            assert not await app.fetchval("SELECT current_setting('app.current_tenant', true)")
        finally:
            await app.close()
        yield SimpleNamespace(admin=admin, app_connection=app_connection, role=role)
    finally:
        if admin is not None:
            await admin.close()
        # Names are generated here, not supplied by environment or user input.
        if db_created:
            await root.execute(f'DROP DATABASE "{dbname}"')
        if role_created:
            await root.execute(f'DROP ROLE "{role}"')
        await root.close()


async def _insert(conn, table, row_id, tenant):
    if table == "decision_outbox_events":
        await conn.execute(
            "INSERT INTO decision_outbox_events "
            "(event_id,tenant_id,event_type,aggregate_type,aggregate_id) "
            "VALUES ($1,$2::uuid,'CI_ONLY','ci_probe',$1)",
            row_id,
            tenant,
        )
    else:
        assert table == "decision_reviews"
        await conn.execute(
            "INSERT INTO decision_reviews "
            "(review_id,decision_id,tenant_id,action,previous_state,new_state,"
            "reviewed_by,candidate_lineage_id,idempotency_key,request_hash,policy_version) "
            "VALUES ($1,$1,$2::uuid,'approve','pending_approval','approved',"
            "'ci-reviewer','ci-lineage',$1,'ci-hash','ci-policy')",
            row_id,
            tenant,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("owns_table", [False, True], ids=["nonowner", "forced-owner"])
async def test_033_isolates_reads_writes_and_rolls_back(database, table, owns_table):
    assert (await runner.apply_migrations())["applied_now"] == [VERSION]
    if owns_table:
        await database.admin.execute(f'ALTER TABLE {table} OWNER TO "{database.role}"')
    app = await database.app_connection()
    try:
        flags = await app.fetchrow(
            "SELECT relrowsecurity, relforcerowsecurity, "
            "pg_get_userbyid(relowner)=current_user AS owns FROM pg_class WHERE oid=$1::regclass",
            table,
        )
        assert tuple(flags) == (True, True, owns_table)
        tx = app.transaction()
        await tx.start()
        try:
            await app.execute("SELECT set_config('app.current_tenant',$1,true)", TENANT)
            await _insert(app, table, "ci-own", TENANT)
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 1
            # Savepoints preserve the outer transaction after expected RLS errors.
            with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
                async with app.transaction():
                    await _insert(app, table, "ci-cross", OTHER)
            await app.execute("SELECT set_config('app.current_tenant',$1,true)", OTHER)
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 0
            await app.execute("SELECT set_config('app.current_tenant','',true)")
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 0
            with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
                async with app.transaction():
                    await _insert(app, table, "ci-missing", TENANT)
        finally:
            await tx.rollback()
        assert not await app.fetchval("SELECT current_setting('app.current_tenant',true)")
        assert await database.admin.fetchval(f"SELECT count(*) FROM {table}") == 0
    finally:
        await app.close()


@pytest.mark.asyncio
async def test_033_runner_check_apply_and_reapply(database):
    before = await runner.check_migrations()
    assert before["pending"] == [VERSION] and not before["ok"]
    assert before["checksum_mismatches"] == []
    first = await runner.apply_migrations()
    assert first["ok"] and first["applied_now"] == [VERSION]
    second = await runner.apply_migrations()
    assert second["ok"] and second["applied_now"] == []
    assert (await runner.check_migrations())["pending"] == []
    assert (
        await database.admin.fetchval(
            "SELECT count(*) FROM decision_service_schema_migrations WHERE version=$1", VERSION
        )
        == 1
    )


@pytest.mark.asyncio
async def test_033_runner_rolls_back_policy_and_journal_on_error(database, monkeypatch):
    migrations = runner.load_migrations()
    target = next(m for m in migrations if m.version == VERSION)
    broken = replace(target, sql=target.sql + "\nSELECT 1 / 0;")
    with monkeypatch.context() as scoped:
        scoped.setattr(
            runner, "load_migrations", lambda: [broken if m == target else m for m in migrations]
        )
        with pytest.raises(asyncpg.DivisionByZeroError):
            await runner.apply_migrations()
    assert (await runner.check_migrations())["pending"] == [VERSION]
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
    assert (await runner.apply_migrations())["ok"]


@pytest.mark.asyncio
async def test_learning_writer_survives_033_under_restricted_login(database):
    payload = SimpleNamespace(
        model_id="ci-model",
        feature_set_id=None,
        learning_rate=0.01,
        sample_count=1,
        label_summary={},
        drift_score=0.0,
        action="ci-only",
        source_type="ci-probe",
        source_id="ci-source",
        field_id=None,
        season_id=None,
        recommendation_id=None,
        decision_id=None,
        evidence_snapshot_id=None,
    )
    # Positive control: the actual writer succeeds before 033 with the SAME role.
    before = await persistence.persist_learning_update(
        tenant_id=TENANT, payload=payload, update_id="ci-before", traceability_status="traceable"
    )
    assert before == {"update_id": "ci-before"}
    assert (await runner.apply_migrations())["ok"]
    try:
        after = await persistence.persist_learning_update(
            tenant_id=TENANT, payload=payload, update_id="ci-after", traceability_status="traceable"
        )
    except asyncpg.InsufficientPrivilegeError:
        # Failed outbox write must roll back the learning row, not leave a partial commit.
        assert (
            await database.admin.fetchval(
                "SELECT count(*) FROM online_learning_updates WHERE update_id='ci-after'"
            )
            == 0
        )
        raise
    assert after == {"update_id": "ci-after"}
    assert (
        await database.admin.fetchval(
            "SELECT count(*) FROM decision_outbox_events WHERE aggregate_id='ci-after'"
        )
        == 1
    )


@pytest.mark.asyncio
async def test_review_idempotency_replay_survives_033_under_restricted_login(database):
    request = dict(
        tenant_id=TENANT,
        decision_id="ci-review",
        action="approve",
        new_state="approved",
        reason="ci-only",
        reviewed_by="ci-reviewer",
        candidate_lineage_id="ci-lineage",
        idempotency_key="ci-review",
        policy_version="ci-policy",
    )
    request_hash = persistence._request_hash(
        **{
            key: request[key]
            for key in ("decision_id", "action", "new_state", "reason", "candidate_lineage_id")
        }
    )
    await database.admin.execute(
        "INSERT INTO decision_record (decision_id,tenant_id,stage,decision_type,"
        "review_state,candidate_lineage_id) "
        "VALUES ('ci-review',$1::uuid,'candidate','crop_decision_candidate','approved','ci-lineage')",
        TENANT,
    )
    await database.admin.execute(
        "INSERT INTO decision_reviews (review_id,decision_id,tenant_id,action,previous_state,"
        "new_state,reason,reviewed_by,candidate_lineage_id,idempotency_key,request_hash,policy_version) "
        "VALUES ('ci-saved-review','ci-review',$1::uuid,'approve','pending_approval','approved',"
        "'ci-only','ci-reviewer','ci-lineage','ci-review',$2,'ci-policy')",
        TENANT,
        request_hash,
    )
    before = await persistence.review_decision(**request)
    assert before["status"] == "ok" and before["replay"] is True
    assert (await runner.apply_migrations())["ok"]
    after = await persistence.review_decision(**request)
    assert after == before, "033 must not hide a tenant's authoritative idempotency replay"
