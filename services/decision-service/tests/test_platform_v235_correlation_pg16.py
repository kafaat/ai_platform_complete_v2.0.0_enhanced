"""Native PG16 proof of v235 on its exact platform target-table migrations.

This is NOT full-platform-schema or deployed-runtime acceptance. Apply unmodified
v66/v67/v68/v78/v178, then v235 twice. The selected subset omits the v9 helper,
so only dispatch/ledger receive explicitly declared canonical fixture RLS below.
The actual v78/v178 policies remain unchanged. No physical command is executed.
"""

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from test_migration_033_pg16 import ADMIN_DSN, OTHER, TENANT, _configured_dsn, _connect

ROOT = Path(__file__).resolve().parents[3]
BASE_MIGRATIONS = (
    "v66_dispatch_decisions.sql",
    "v67_dispatch_hardening.sql",
    "v68_execution_ledger.sql",
    "v78_decision_record.sql",
    "v178_canonical_as_applied_irrigation_truth.sql",
)
TABLES = (
    "dispatch_decisions",
    "execution_ledger",
    "decision_record",
    "as_applied_irrigation_runs",
    "as_applied_irrigation_receipts",
)


async def dispatch(conn, row_id, tenant=TENANT, correlation=None):
    return await conn.fetchval(
        "INSERT INTO dispatch_decisions(decision_id,tenant_id,recommendation_id,"
        "action_type,state,risk_level,correlation_id) "
        "VALUES($1,$2::uuid,'ci-rec','inspection','blocked','low',$3) RETURNING correlation_id",
        row_id,
        tenant,
        correlation,
    )


async def decision(conn, row_id, tenant=TENANT, correlation=None):
    return await conn.fetchval(
        "INSERT INTO decision_record(decision_id,tenant_id,decision_type,decision_value,"
        "correlation_id) VALUES($1,$2::uuid,'inspection','{}',$3) RETURNING correlation_id",
        row_id,
        tenant,
        correlation,
    )


async def ledger(conn, row_id, parent, correlation=None, outcome="executed"):
    return await conn.fetchval(
        "INSERT INTO execution_ledger(ledger_id,tenant_id,decision_id,action_type,outcome,"
        "content_hash,correlation_id) VALUES($1,$2::uuid,$3,'inspection',$4,'unchanged',$5) "
        "RETURNING correlation_id",
        row_id,
        TENANT,
        parent,
        outcome,
        correlation,
    )


async def physical_run(conn, row_id, parent, correlation=None):
    return await conn.fetchval(
        "INSERT INTO as_applied_irrigation_runs(id,tenant_id,field_id,season_id,machine_id,"
        "controller_id,decision_id,authorization_id,execution_plan_id,plan_digest,"
        "planned_depth_mm,planned_volume_m3,planned_area_ha,irrigation_capability_digest,"
        "commissioning_certification_digest,decision_content_digest,correlation_id) "
        "VALUES($1,$2::uuid,'ci-field','ci-season',$1,$1,$3,'ci-auth',$1::uuid::text,"
        "'digest',1,1,1,'digest','digest','digest',$4) RETURNING correlation_id",
        row_id,
        TENANT,
        parent,
        correlation,
    )


async def receipt(conn, row_id, run_id):
    return await conn.fetchval(
        "INSERT INTO as_applied_irrigation_receipts(id,tenant_id,run_id,controller_id,"
        "receipt_id,state,sequence_number,observed_at,controller_command_digest,"
        "payload_digest,receipt_digest) "
        "VALUES($1,$2::uuid,$3,$3,'ci-receipt','accepted',0,now(),'digest','digest','digest') "
        "RETURNING correlation_id",
        row_id,
        TENANT,
        run_id,
    )


@pytest_asyncio.fixture
async def platform_db():
    # Reuse the exact loopback allowlist and native-major requirement, but NOT the
    # Decision fixture's 001..032 schema: these are different table owners/shapes.
    root = await _connect(_configured_dsn())
    suffix = uuid4().hex
    dbname, role = f"platform235_{suffix}", f"platform235_app_{suffix}"
    admin = app = None
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
        admin = await _connect(urlunsplit(parts._replace(path=f"/{dbname}")))
        for name in BASE_MIGRATIONS:
            await admin.execute((ROOT / "migrations" / name).read_text())
        await admin.execute(
            "INSERT INTO execution_ledger(ledger_id,tenant_id,decision_id,action_type,"
            "outcome,content_hash) VALUES('historical-orphan',$1::uuid,'missing',"
            "'inspection','executed','unchanged')",
            TENANT,
        )
        await admin.execute(
            "INSERT INTO dispatch_decisions(decision_id,tenant_id,recommendation_id,"
            "action_type,state,risk_level) "
            "VALUES('historical-dispatch',$1::uuid,'ci-rec','inspection','blocked','low')",
            TENANT,
        )
        await admin.execute(
            "INSERT INTO decision_record(decision_id,tenant_id,decision_type,decision_value) "
            "VALUES('historical-decision',$1::uuid,'inspection','{}')",
            TENANT,
        )
        migration = (ROOT / "migrations/v235_decision_chain_correlation.sql").read_text()
        await admin.execute(migration)
        await admin.execute(migration)
        for table in ("dispatch_decisions", "execution_ledger"):
            # This fixture policy is explicit; it does not pretend the omitted
            # full-platform RLS migration chain has been tested.
            await admin.execute(
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY; "
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY; "
                f"CREATE POLICY ci_canonical_tenant ON {table} "
                "USING(tenant_id::text=NULLIF(current_setting('app.current_tenant',true),'')) "
                "WITH CHECK(tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''))"
            )
        await admin.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')
        await admin.execute(
            f'GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA public TO "{role}"'
        )
        await dispatch(admin, "foreign-dispatch", OTHER)
        await decision(admin, "foreign-decision", OTHER)
        app = await _connect(
            urlunsplit(
                parts._replace(
                    netloc=f"{role}:disposable_test_only@127.0.0.1:5436", path=f"/{dbname}"
                )
            )
        )
        identity = await app.fetchrow(
            "SELECT current_user=session_user AS actual_login,rolsuper,rolbypassrls,"
            "rolinherit,rolcanlogin FROM pg_roles WHERE rolname=current_user"
        )
        assert tuple(identity) == (True, False, False, False, True)
        assert not await app.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_auth_members "
            "WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user))"
        )
        for table in TABLES:
            flags = await app.fetchrow(
                "SELECT relrowsecurity,relforcerowsecurity,pg_get_userbyid(relowner)=current_user "
                "FROM pg_class WHERE oid=$1::regclass",
                table,
            )
            assert tuple(flags) == (True, True, False)
        await app.execute("SELECT set_config('app.current_tenant',$1,false)", TENANT)
        yield SimpleNamespace(admin=admin, app=app)
    finally:
        if app is not None:
            await app.close()
        if admin is not None:
            await admin.close()
        if db_created:
            await root.execute(f'DROP DATABASE "{dbname}"')
        if role_created:
            await root.execute(f'DROP ROLE "{role}"')
        await root.close()


@pytest.mark.asyncio
async def test_historical_orphan_remains_null(platform_db):
    row = await platform_db.app.fetchrow(
        "SELECT correlation_id,content_hash FROM execution_ledger WHERE ledger_id='historical-orphan'"
    )
    assert tuple(row) == (None, "unchanged")


@pytest.mark.asyncio
async def test_new_orphan_ledger_stays_unbound(platform_db):
    assert await ledger(platform_db.app, "orphan", "missing") is None


@pytest.mark.asyncio
async def test_missing_physical_decision_stays_unbound(platform_db):
    assert await physical_run(platform_db.app, uuid4(), "missing") is None


@pytest.mark.asyncio
async def test_foreign_dispatch_is_invisible_and_not_inherited(platform_db):
    assert (
        await platform_db.app.fetchval(
            "SELECT count(*) FROM dispatch_decisions WHERE decision_id='foreign-dispatch'"
        )
        == 0
    )
    assert await ledger(platform_db.app, "foreign-reference", "foreign-dispatch") is None


@pytest.mark.asyncio
async def test_foreign_agronomic_decision_is_invisible_and_not_inherited(platform_db):
    assert (
        await platform_db.app.fetchval(
            "SELECT count(*) FROM decision_record WHERE decision_id='foreign-decision'"
        )
        == 0
    )
    assert await physical_run(platform_db.app, uuid4(), "foreign-decision") is None


@pytest.mark.asyncio
async def test_caller_cannot_forge_orphan_correlation(platform_db):
    with pytest.raises(asyncpg.CheckViolationError, match="visible same-tenant parent"):
        await ledger(platform_db.app, "forged", "missing", uuid4())


@pytest.mark.asyncio
async def test_dispatch_child_inherits_stored_identity(platform_db):
    correlation = await dispatch(platform_db.app, "own-dispatch")
    assert isinstance(correlation, UUID)
    assert await ledger(platform_db.app, "bound", "own-dispatch") == correlation
    with pytest.raises(asyncpg.CheckViolationError, match="conflicts with parent"):
        await ledger(platform_db.app, "forged-child", "own-dispatch", uuid4())


@pytest.mark.asyncio
async def test_original_outcome_constraint_still_rejects_queued(platform_db):
    with pytest.raises(asyncpg.CheckViolationError, match="execution_ledger_outcome_check"):
        await ledger(platform_db.app, "bad-outcome", "missing", outcome="queued")


@pytest.mark.asyncio
async def test_physical_run_and_receipt_inherit_without_digest_rewrite(platform_db):
    correlation = await decision(platform_db.app, "physical-parent")
    run_id = uuid4()
    assert await physical_run(platform_db.app, run_id, "physical-parent") == correlation
    assert await receipt(platform_db.app, uuid4(), run_id) == correlation
    assert (
        await platform_db.app.fetchval(
            "SELECT trim(decision_content_digest) FROM as_applied_irrigation_runs WHERE id=$1",
            run_id,
        )
        == "digest"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("table", TABLES)
async def test_correlation_identity_is_immutable(platform_db, table):
    await dispatch(platform_db.app, "own-dispatch")
    await ledger(platform_db.app, "bound", "own-dispatch")
    await decision(platform_db.app, "own-decision")
    run_id = uuid4()
    await physical_run(platform_db.app, run_id, "own-decision")
    await receipt(platform_db.app, uuid4(), run_id)
    with pytest.raises(asyncpg.CheckViolationError, match="identity is immutable"):
        await platform_db.app.execute(f"UPDATE {table} SET correlation_id=gen_random_uuid()")


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", [dispatch, decision])
async def test_roots_reject_caller_supplied_identity(platform_db, writer):
    with pytest.raises(asyncpg.CheckViolationError, match="server-owned"):
        await writer(platform_db.app, "forged-root", correlation=uuid4())


@pytest.mark.asyncio
async def test_historical_parent_identity_is_not_invented(platform_db):
    assert await ledger(platform_db.app, "historical-child", "historical-dispatch") is None
    assert await physical_run(platform_db.app, uuid4(), "historical-decision") is None
