"""Disposable PG16 proof for 037: FORCE RLS on the remaining decision tenant tables.

The production shape is a runtime role that OWNS the decision tables (migrations run
under the same DATABASE_URL). Without FORCE that owner bypasses every policy; with FORCE
the policies apply to it. So every case here hands table ownership to the fresh
NOSUPERUSER NOBYPASSRLS login from the 033 fixture and then drives the real persistence
functions as that owner: a read path that forgets to bind its identity returns nothing
here, exactly as it would in production.

decision_record is additionally FORCEd to mirror the shared database, where the platform
chain (migrations/v78) forces it; in this decision-only database 019 only enables it.

Runs only in the dedicated loopback CI database (see test_migration_033_pg16).
"""

from __future__ import annotations

from types import SimpleNamespace

import asyncpg
import migration_runner as runner
import persistence
import pytest
from test_decision_tenant_tables_force_rls_static import _PLATFORM_HARDENED
from test_migration_033_pg16 import OTHER, TENANT
from test_migration_033_pg16 import database as database

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# A request id, not a credential (named so secret scanners do not read it as an assigned key).
_ATTRIBUTION_REQUEST = "ci-attribution-037"

WORKER = "ci-worker-037"
STRANGER = "ci-worker-037-unregistered"
THIRD = "00000000-0000-0000-0000-000000000035"

# The v206 catalog predicate (migrations/v206_rls_final_hardening.sql step 2), verbatim
# apart from the platform-owned exclusions this decision-only database does not harden.
V206_OFFENDERS = """
SELECT coalesce(string_agg(t.tablename, ', ' ORDER BY t.tablename), '')
FROM pg_tables t
WHERE t.schemaname = 'public'
  AND NOT (t.tablename = ANY($1::text[]))
  AND EXISTS (SELECT 1 FROM information_schema.columns c
              WHERE c.table_schema = 'public' AND c.table_name = t.tablename
                AND c.column_name = 'tenant_id')
  AND (
      NOT t.rowsecurity
      OR NOT EXISTS (SELECT 1 FROM pg_class c
                     WHERE c.relname = t.tablename
                       AND c.relnamespace = 'public'::regnamespace
                       AND c.relforcerowsecurity)
      OR NOT EXISTS (SELECT 1 FROM pg_policies p
                     WHERE p.schemaname = 'public' AND p.tablename = t.tablename
                       AND p.cmd IN ('ALL', 'INSERT', 'UPDATE')
                       AND p.with_check IS NOT NULL)
  )
"""


async def _apply_and_hand_ownership(database) -> None:
    assert (await runner.apply_migrations())["ok"]
    tables = await database.admin.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    for row in tables:
        await database.admin.execute(f'ALTER TABLE "{row["tablename"]}" OWNER TO "{database.role}"')
    await database.admin.execute("ALTER TABLE decision_record FORCE ROW LEVEL SECURITY")
    owner = await database.admin.fetchval(
        "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE relname='decision_execution_requests'"
    )
    assert owner == database.role


async def _count_as_owner(database, table: str, *, tenant=None, worker=None) -> int:
    conn = await database.app_connection()
    try:
        async with conn.transaction():
            if tenant is not None:
                await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            if worker is not None:
                await conn.execute("SELECT set_config('app.current_worker', $1, true)", worker)
            return await conn.fetchval(f"SELECT count(*) FROM {table}")
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_037_satisfies_the_v206_catalog_assertion(database):
    assert (await runner.apply_migrations())["ok"]
    offenders = await database.admin.fetchval(V206_OFFENDERS, sorted(_PLATFORM_HARDENED))
    assert offenders == ""
    # Re-running 037 (as every deploy may) changes nothing and still passes.
    sql = next(m.sql for m in runner.load_migrations() if m.version.startswith("037_"))
    await database.admin.execute(sql)
    assert await database.admin.fetchval(V206_OFFENDERS, sorted(_PLATFORM_HARDENED)) == ""


@pytest.mark.asyncio
async def test_group_b_write_and_read_are_tenant_bound_for_the_owner(database):
    await _apply_and_hand_ownership(database)
    first = await persistence.record_reservation_dispatch_intent(
        tenant_id=TENANT,
        source_event_id="ci-evt-037",
        event_type="irrigation.reservation.dispatch_requested",
        payload=SimpleNamespace(evaluation_id="ci-eval", reservation_ids=["r1"]),
    )
    assert first["status"] == "received", first
    replay = await persistence.record_reservation_dispatch_intent(
        tenant_id=TENANT,
        source_event_id="ci-evt-037",
        event_type="irrigation.reservation.dispatch_requested",
        payload=SimpleNamespace(evaluation_id="ci-eval", reservation_ids=["r1"]),
    )
    assert replay["status"] == "duplicate", replay
    table = "decision_reservation_dispatch_inbox"
    assert await _count_as_owner(database, table, tenant=TENANT) == 1
    assert await _count_as_owner(database, table, tenant=OTHER) == 0
    assert await _count_as_owner(database, table) == 0  # no setting: fail-closed
    assert await database.admin.fetchval(f"SELECT count(*) FROM {table}") == 1
    # An unbound write by the owner is refused by WITH CHECK (FORCE applies to the owner).
    conn = await database.app_connection()
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO decision_reservation_dispatch_inbox (inbox_id,tenant_id,"
                "source_event_id,event_type,reservation_ids,payload,dispatch_state,receipt_id,"
                "request_hash) VALUES ('ci-x',$1::uuid,'ci-x','irrigation.reservation."
                "dispatch_requested','[]','{}','received','ci-x','ci-x')",
                TENANT,
            )
    finally:
        await conn.close()


async def _governed_decision(database):
    import main as api
    import test_agronomic_lineage_integrity as lineage

    async def call(name, **kwargs):
        result = await getattr(persistence, name)(tenant_id=TENANT, **kwargs)
        assert result.get("status", "ok") == "ok", (name, result)
        return result

    veg = await call(
        "persist_vegetation_snapshot",
        payload=lineage._veg_payload("ci-field-037", "c" * 64),
        snapshot_id="ci-veg-037",
    )
    ctx = await call(
        "compose_agronomic_context",
        created_by="ci",
        payload=lineage._compose_payload("ci-field-037"),
    )
    manifest_hash = await database.admin.fetchval(
        "SELECT content_hash FROM decision_feature_manifests WHERE feature_manifest_id=$1",
        ctx["feature_manifest_id"],
    )
    await call(
        "persist_decision_record",
        decision_id="ci-decision-037",
        payload=lineage._decision("ci-field-037", ctx, veg["snapshot_id"], manifest_hash),
    )
    return api, ctx


@pytest.mark.asyncio
async def test_evidence_context_and_calibration_reads_return_the_tenants_rows(database):
    await _apply_and_hand_ownership(database)
    api, ctx = await _governed_decision(database)

    snapshot = await persistence.get_context_snapshot(
        tenant_id=TENANT, snapshot_id=ctx["snapshot_id"]
    )
    assert snapshot["status"] == "ok"
    assert await persistence.get_context_snapshot(
        tenant_id=OTHER, snapshot_id=ctx["snapshot_id"]
    ) == {"status": "not_found"}

    evidence = await persistence.get_decision_agronomic_evidence(
        tenant_id=TENANT, decision_id="ci-decision-037"
    )
    assert evidence["status"] == "ok"
    assert evidence["context_snapshot"]["snapshot_id"] == ctx["snapshot_id"]
    assert evidence["historical_snapshot"] is not None
    assert evidence["feature_manifest"]["entries"]
    assert evidence["vegetation_snapshot"]["snapshot_id"] == "ci-veg-037"
    assert evidence["evidence_complete"] is True
    assert await persistence.get_decision_agronomic_evidence(
        tenant_id=OTHER, decision_id="ci-decision-037"
    ) == {"status": "not_found"}

    await database.admin.execute(
        "INSERT INTO outcome_record(outcome_id,tenant_id,decision_id,success,verification_state,"
        "evidence_snapshot_id,execution_request_id) "
        "VALUES('ci-outcome-037',$1::uuid,'ci-decision-037',true,'verified_success',"
        "'ci-evidence-037','ci-execution-037')",
        TENANT,
    )
    attribution = await persistence.create_learning_attribution(
        tenant_id=TENANT,
        outcome_id="ci-outcome-037",
        attributed_by="ci",
        payload=api.LearningAttributionIn(
            model_id="ci-model-037",
            feature_set_id="f1",
            label="success",
            evidence_snapshot_id="ci-evidence-037",
            idempotency_key=_ATTRIBUTION_REQUEST,
        ),
    )
    assert attribution["status"] == "ok", attribution
    dataset = await persistence.build_calibration_dataset(
        tenant_id=TENANT, model_id="ci-model-037", feature_set_id="f1", limit=10
    )
    assert dataset["count"] == 1
    assert dataset["items"][0]["decision_id"] == "ci-decision-037"
    other = await persistence.build_calibration_dataset(
        tenant_id=OTHER, model_id="ci-model-037", feature_set_id="f1", limit=10
    )
    assert other["count"] == 0
    for table in (
        "decision_agronomic_context_snapshots",
        "decision_feature_manifests",
        "decision_vegetation_snapshots",
        "decision_learning_attributions",
        "decision_record",
    ):
        assert await _count_as_owner(database, table) == 0, table
        assert await _count_as_owner(database, table, tenant=TENANT) >= 1, table


@pytest.mark.asyncio
async def test_runtime_work_feed_and_active_state_under_force(database):
    from _model_chain import seed_activated_model

    await _apply_and_hand_ownership(database)
    ids = await seed_activated_model(database.admin, tenant=TENANT, model_id="ci-model-037")

    state = await persistence.get_active_model_state(
        tenant_id=TENANT,
        model_id="ci-model-037",
        feature_set_id="f1",
        target_environment="staging",
    )
    assert state["status"] == "ok"
    assert state["source_receipt_id"] == ids["activation_receipt_id"]
    assert (
        await persistence.get_active_model_state(
            tenant_id=OTHER,
            model_id="ci-model-037",
            feature_set_id="f1",
            target_environment="staging",
        )
    )["status"] == "not_found"

    work = await persistence.list_runtime_work(tenant_id=TENANT, worker_id=WORKER)
    verification = [i for i in work["items"] if i["work_type"] == "post_activation_verification"]
    assert len(verification) == 1
    assert verification[0]["payload"]["activation_receipt_id"] == ids["activation_receipt_id"]
    assert verification[0]["payload"]["work_claim_id"].startswith("wkclaim_")
    # The lease was written by the owner under FORCE and committed with the feed read.
    assert await _count_as_owner(database, "decision_model_runtime_work_claims", tenant=TENANT) == 1
    assert await _count_as_owner(database, "decision_model_runtime_work_claims") == 0
    # A second replica sees the item but loses the live lease.
    again = await persistence.list_runtime_work(tenant_id=TENANT, worker_id="ci-other-replica")
    assert not [i for i in again["items"] if i["work_type"] == "post_activation_verification"]
    assert (await persistence.list_runtime_work(tenant_id=OTHER, worker_id=WORKER))["items"] == []


@pytest.mark.asyncio
async def test_worker_tables_are_worker_partitioned_and_authorization_stays_fail_closed(
    database, monkeypatch
):
    await _apply_and_hand_ownership(database)
    for tenant, key in ((TENANT, "k-037-a"), (OTHER, "k-037-b")):
        result = await persistence.register_runtime_worker_tenant(
            worker_id=WORKER,
            created_by="ci-operator",
            payload=SimpleNamespace(tenant_id=tenant, enabled=True, idempotency_key=key),
        )
        assert result["status"] == "ok" and result["replay"] is False, result

    # Replay lookup is cross-tenant: the same key for ANOTHER tenant is a typed conflict
    # (409), not a UniqueViolation (500) from an invisible prior command.
    conflict = await persistence.register_runtime_worker_tenant(
        worker_id=WORKER,
        created_by="ci-operator",
        payload=SimpleNamespace(tenant_id=THIRD, enabled=True, idempotency_key="k-037-a"),
    )
    assert conflict == {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}

    listed = await persistence.list_worker_tenants(worker_id=WORKER)
    assert listed == {"worker_id": WORKER, "registered": True, "tenants": sorted([TENANT, OTHER])}
    assert (await persistence.list_worker_tenants(worker_id=STRANGER))["registered"] is False

    for strict in ("", "true"):
        monkeypatch.setenv("DECISION_STRICT_WORKER_TENANTS", strict)
        assert await persistence.worker_tenant_authorized(worker_id=WORKER, tenant_id=TENANT)
        assert await persistence.worker_tenant_authorized(worker_id=WORKER, tenant_id=OTHER)
        # Registered worker, unregistered tenant: denied in BOTH modes, i.e. the probe found
        # the registration and never fell into the legacy "unregistered -> allow" branch.
        assert not await persistence.worker_tenant_authorized(worker_id=WORKER, tenant_id=THIRD)
    monkeypatch.setenv("DECISION_STRICT_WORKER_TENANTS", "true")
    assert not await persistence.worker_tenant_authorized(worker_id=STRANGER, tenant_id=TENANT)
    monkeypatch.setenv("DECISION_STRICT_WORKER_TENANTS", "")
    assert await persistence.worker_tenant_authorized(worker_id=STRANGER, tenant_id=TENANT)

    for table in ("decision_runtime_worker_tenants", "decision_runtime_worker_tenant_commands"):
        assert await _count_as_owner(database, table) == 0, table
        assert await _count_as_owner(database, table, worker=WORKER) == 2, table
        assert await _count_as_owner(database, table, worker=STRANGER) == 0, table
        assert await _count_as_owner(database, table, tenant=TENANT) == 1, table

    # The worker binding grants reads only: no write into any tenant, no cross-tenant update.
    conn = await database.app_connection()
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_worker', $1, true)", WORKER)
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute(
                    "INSERT INTO decision_runtime_worker_tenants (registration_id,worker_id,"
                    "tenant_id,created_by,idempotency_key,request_hash) VALUES ('ci-x',$1,"
                    "$2::uuid,'ci','ci-x',$3)",
                    WORKER,
                    THIRD,
                    "a" * 64,
                )
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_worker', $1, true)", WORKER)
            updated = await conn.execute(
                "UPDATE decision_runtime_worker_tenants SET enabled=false WHERE worker_id=$1",
                WORKER,
            )
            assert updated == "UPDATE 0"
            deleted = await conn.execute(
                "DELETE FROM decision_runtime_worker_tenants WHERE worker_id=$1", WORKER
            )
            assert deleted == "DELETE 0"
    finally:
        await conn.close()
    assert (await persistence.list_worker_tenants(worker_id=WORKER))["tenants"] == sorted(
        [TENANT, OTHER]
    )
