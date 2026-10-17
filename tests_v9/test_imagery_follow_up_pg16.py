"""Real PG16 queue/RLS/lease witnesses on an exact disposable loopback target only."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[1]
ADMIN_DSN = "postgresql://followup_admin:disposable_test_only@127.0.0.1:5437/followup_test"
TENANT = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"


@pytest_asyncio.fixture
async def database(monkeypatch):
    configured = os.getenv("FOLLOWUP_TEST_DATABASE_URL", "")
    if not configured:
        if os.getenv("FOLLOWUP_REQUIRE_PG16") == "1":
            pytest.fail("required disposable PG16 witness is unavailable")
        pytest.skip("requires dedicated disposable loopback PG16")
    if configured != ADMIN_DSN:
        pytest.fail("refusing non-disposable PostgreSQL target")
    monkeypatch.syspath_prepend(str(ROOT / "services/raster-service"))
    import follow_up_store

    root = await asyncpg.connect(ADMIN_DSN, command_timeout=15)
    suffix = uuid4().hex
    dbname, role = "followup_" + suffix, "followup_app_" + suffix
    created_db = created_role = False
    admin = None
    try:
        version = int(await root.fetchval("SHOW server_version_num"))
        assert 160000 <= version < 170000
        await root.execute(f'CREATE DATABASE "{dbname}"')
        created_db = True
        await root.execute(
            f"CREATE ROLE \"{role}\" LOGIN PASSWORD 'disposable_test_only' NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB NOINHERIT"
        )
        created_role = True
        admin = await asyncpg.connect(
            ADMIN_DSN.rsplit("/", 1)[0] + "/" + dbname, command_timeout=15
        )
        ddl = (ROOT / "migrations/v236_raster_follow_up_requests.sql").read_text()
        await admin.execute(ddl)
        await admin.execute(ddl)  # additive/idempotent on the exact migration bytes
        await admin.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')
        await admin.execute(
            f'GRANT SELECT, INSERT, UPDATE ON raster_follow_up_requests TO "{role}"'
        )

        async def connect():
            return await asyncpg.connect(
                user=role,
                password="disposable_test_only",
                host="127.0.0.1",
                port=5437,
                database=dbname,
                command_timeout=10,
                server_settings={"lock_timeout": "3s"},
            )

        conn = await connect()
        try:
            flags = await conn.fetchrow(
                "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
            )
            assert not flags["rolsuper"] and not flags["rolbypassrls"]
            assert await conn.fetchval("SELECT current_user") == role
        finally:
            await conn.close()
        yield SimpleNamespace(
            admin=admin,
            connect=connect,
            store=follow_up_store.FollowUpStore(connect),
            module=follow_up_store,
            role=role,
        )
    finally:
        if admin:
            await admin.close()
        if created_db:
            await root.execute(f'DROP DATABASE "{dbname}"')
        if created_role:
            await root.execute(f'DROP ROLE "{role}"')
        await root.close()


def args(tenant=TENANT, identity="request-1", *, future=False, expired=False):
    due = datetime.now(UTC) + timedelta(days=1 if future else -2)
    return dict(
        tenant=tenant,
        request_id=identity,
        field_id="field",
        request_hash="a" * 64,
        payload={"time_basis": "delivery_receipt_received_at", "receipt_id": "receipt"},
        due_at=due,
        expires_at=due + timedelta(days=1 if expired else 7),
    )


async def test_concurrent_replay_and_payload_conflict(database):
    rows = await asyncio.gather(*(database.store.enqueue(**args()) for _ in range(12)))
    assert {r["request_id"] for r in rows} == {"request-1"}
    assert await database.admin.fetchval("SELECT count(*) FROM raster_follow_up_requests") == 1
    with pytest.raises(database.module.RequestConflict):
        await database.store.enqueue(**{**args(), "request_hash": "b" * 64})
    restored = database.module.FollowUpStore(database.connect)
    assert (await restored.get(TENANT, "request-1"))["request_hash"] == "a" * 64


@pytest.mark.parametrize("owner", [False, True])
async def test_real_role_rls_read_write_and_missing_context(database, owner):
    await database.store.enqueue(**args())
    await database.store.enqueue(**args(OTHER))  # same natural ID remains tenant-local
    if owner:
        await database.admin.execute(
            f'ALTER TABLE raster_follow_up_requests OWNER TO "{database.role}"'
        )
    conn = await database.connect()
    try:
        assert await conn.fetchval("SELECT count(*) FROM raster_follow_up_requests") == 0
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant',$1,true)", TENANT)
            assert await conn.fetchval("SELECT count(*) FROM raster_follow_up_requests") == 1
            assert (
                await conn.execute(
                    "UPDATE raster_follow_up_requests SET reason_code='forged' WHERE tenant_id=$1::uuid",
                    OTHER,
                )
                == "UPDATE 0"
            )
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE raster_follow_up_requests SET tenant_id=$1::uuid", OTHER
                    )
        assert await conn.fetchval("SELECT count(*) FROM raster_follow_up_requests") == 0
    finally:
        await conn.close()


async def test_no_early_claim_and_expiry_are_persistent(database):
    await database.store.enqueue(**args(identity="future", future=True))
    await database.store.enqueue(**args(identity="expired", expired=True))
    assert await database.store.claim(TENANT) is None
    assert (await database.store.get(TENANT, "future"))["status"] == "pending"
    expired = await database.store.get(TENANT, "expired")
    assert expired["status"] == "expired"
    assert expired["reason_code"] == "observation_window_expired"


async def test_only_one_concurrent_claim_and_stale_worker_cannot_finish(database):
    await database.store.enqueue(**args())
    claims = await asyncio.gather(*(database.store.claim(TENANT) for _ in range(10)))
    winners = [r for r in claims if r is not None]
    assert len(winners) == 1
    old = winners[0]
    await database.admin.execute(
        "UPDATE raster_follow_up_requests SET lease_until=now()-interval '1 second'"
    )
    assert not await database.store.settle(old, status="failed", reason="late")
    recovered = await database.module.FollowUpStore(database.connect).claim(TENANT)
    assert recovered["lease_token"] != old["lease_token"]
    assert recovered["attempts"] == 2
    assert not await database.store.save_progress(old, {"scene": "forged"})
    assert await database.store.settle(
        recovered, status="dispatched", result={"jobs": [{"item_id": 1}]}
    )
    assert await database.store.claim(TENANT) is None


async def test_progress_survives_retry_and_worker_loss(database):
    await database.store.enqueue(**args())
    claim = await database.store.claim(TENANT)
    progress = {"scene": {"item_id": "scene-1"}, "jobs": [{"indicator": "ndvi", "item_id": 1}]}
    assert await database.store.save_progress(claim, progress)
    assert await database.store.settle(
        claim, status="retry_wait", reason="catalog_unavailable", delay_seconds=60
    )
    assert await database.store.claim(TENANT) is None
    assert (await database.store.get(TENANT, "request-1"))["result_payload"] == progress
    await database.admin.execute(
        "UPDATE raster_follow_up_requests SET next_attempt_at=now()-interval '1 second'"
    )
    restored = await database.module.FollowUpStore(database.connect).claim(TENANT)
    assert restored["result_payload"] == progress
    assert restored["attempts"] == 2


async def test_cancellation_and_budget_are_honest_terminal_states(database):
    await database.store.enqueue(**args(identity="cancel"))
    assert await database.store.cancel(TENANT, "cancel")
    assert not await database.store.cancel(TENANT, "cancel")
    assert await database.store.claim(TENANT) is None
    await database.store.enqueue(**args(identity="budget"))
    await database.admin.execute(
        "UPDATE raster_follow_up_requests SET attempts=128 WHERE request_id='budget'"
    )
    assert await database.store.claim(TENANT) is None
    assert (await database.store.get(TENANT, "budget"))["reason_code"] == "attempt_budget_exhausted"


async def test_authoritative_receipt_query_uses_matching_accepted_tenant_rows(
    database, monkeypatch
):
    """Actual query + existing table DDL; not a full SoR promotion certification."""
    import importlib.util
    import sys

    migrations = ROOT / "services/decision-service/migrations"
    for name in (
        "001_decision_sor.sql",
        "005_execution_request.sql",
        "006_execution_delivery_receipt.sql",
    ):
        await database.admin.execute((migrations / name).read_text())
    # The exact additive column from 019; its unrelated lineage FKs are outside this fixture.
    season_ddl = next(
        line
        for line in (migrations / "019_agronomic_lineage_integrity.sql").read_text().splitlines()
        if line.startswith("ALTER TABLE decision_record ADD COLUMN IF NOT EXISTS season_id")
    )
    await database.admin.execute(season_ddl)
    await database.admin.execute(
        f'GRANT SELECT ON decision_record, decision_execution_requests, decision_execution_delivery_attempts TO "{database.role}"'
    )
    monkeypatch.setitem(sys.modules, "persistence", SimpleNamespace(_connect=database.connect))
    spec = importlib.util.spec_from_file_location(
        "receipt_query_witness", ROOT / "services/decision-service/observation_context.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    anchor = datetime.now(UTC) - timedelta(days=2)
    for i, (tenant, status, request_receipt, attempt_receipt) in enumerate(
        [
            (TENANT, "accepted", "ok", "ok"),
            (TENANT, "failed", "failed", "failed"),
            (TENANT, "accepted", "request", "different"),
            (OTHER, "accepted", "other", "other"),
        ]
    ):
        key = f"case-{i}"
        await database.admin.execute(
            "INSERT INTO decision_record(decision_id,tenant_id,field_id,season_id) VALUES($1,$2::uuid,'field','season')",
            key,
            tenant,
        )
        await database.admin.execute(
            """INSERT INTO decision_execution_requests
          (execution_request_id,tenant_id,dispatch_authorization_id,execution_plan_id,decision_id,
           target_type,target_id,operation_type,status,idempotency_key,request_hash,requested_by,
           receipt_id,receipt_status,received_at)
          VALUES($1,$2::uuid,$1,$1,$1,'task','task','observe',$3,$1,'hash','test',$4,$3,$5)""",
            key,
            tenant,
            status,
            request_receipt,
            anchor,
        )
        await database.admin.execute(
            """INSERT INTO decision_execution_delivery_attempts
          (delivery_attempt_id,tenant_id,execution_request_id,adapter_id,adapter_kind,delivery_token_hash,
           receipt_id,receipt_status,received_at)
          VALUES($1,$2::uuid,$1,'test','task','hash',$3,$4,$5)""",
            key,
            tenant,
            attempt_receipt,
            status,
            anchor,
        )
    result = await module.read_context(TENANT, "case-0")
    assert result["received_at"] == anchor.isoformat()
    assert result["field_id"] == "field" and result["season_id"] == "season"
    assert result["time_basis"] == "delivery_receipt_received_at"
    assert result["physical_execution_verified"] is False
    for key in ("case-1", "case-2", "case-3", "absent"):
        assert await module.read_context(TENANT, key) is None
    assert await module.read_context(OTHER, "case-0") is None


async def test_schema_rejects_orphaned_lease(database):
    await database.store.enqueue(**args())
    with pytest.raises(asyncpg.CheckViolationError):
        await database.admin.execute("UPDATE raster_follow_up_requests SET lease_token=$1", uuid4())
    with pytest.raises(asyncpg.CheckViolationError):
        await database.admin.execute("UPDATE raster_follow_up_requests SET lease_until=now()")
