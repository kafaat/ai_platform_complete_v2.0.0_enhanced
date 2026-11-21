from __future__ import annotations

import asyncio
import os
import uuid
from types import SimpleNamespace

import pytest
import raster_batch_job_store as store

DB_URL = os.getenv("RASTER_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DB_URL, reason="RASTER_TEST_DATABASE_URL is not configured")


async def _cleanup(claim_key: str, tenant_id: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(DB_URL, statement_cache_size=0)
    try:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)
        await conn.execute("DELETE FROM raster_batch_jobs WHERE claim_key=$1", claim_key)
    finally:
        await conn.close()


def _req(tenant_id: str):
    return SimpleNamespace(
        model_dump=lambda mode="json": {
            "tenant_id": tenant_id,
            "field_id": "fld_runtime_cert",
            "raster_url": "s3://runtime-cert/scene.tif",
            "indicators": ["ndvi", "ndmi"],
        }
    )


def test_database_connection_uses_an_unprivileged_nonowner_role():
    """Measure the supplied connection's role, rather than trusting its DSN label."""
    import asyncpg

    async def scenario():
        conn = await asyncpg.connect(DB_URL, statement_cache_size=0)
        try:
            role = await conn.fetchrow(
                "SELECT oid, session_user AS session_role, current_user AS active_role, "
                "rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolreplication "
                "FROM pg_roles WHERE rolname=current_user"
            )
            assert role is not None
            assert role["session_role"] == role["active_role"]
            if expected_role := os.getenv("SAHOOL_TEST_PGROLE"):
                assert role["active_role"] == expected_role
            for attribute in (
                "rolsuper",
                "rolbypassrls",
                "rolcreatedb",
                "rolcreaterole",
                "rolreplication",
            ):
                assert role[attribute] is False, f"application role must not have {attribute}"

            tables = await conn.fetch(
                "SELECT relname, relowner=$1::oid AS owned_by_role FROM pg_class "
                "WHERE oid=ANY(ARRAY['raster_batch_jobs'::regclass, "
                "'backfill_runs'::regclass, 'backfill_run_items'::regclass])",
                role["oid"],
            )
            assert {table["relname"] for table in tables} == {
                "raster_batch_jobs",
                "backfill_runs",
                "backfill_run_items",
            }
            assert not any(table["owned_by_role"] for table in tables), tables

            memberships = await conn.fetch(
                "WITH RECURSIVE membership(roleid) AS ("
                " SELECT roleid FROM pg_auth_members WHERE member=$1::oid"
                " UNION"
                " SELECT grant_row.roleid FROM pg_auth_members grant_row"
                " JOIN membership parent ON grant_row.member=parent.roleid"
                ") SELECT r.rolname FROM membership m JOIN pg_roles r ON r.oid=m.roleid "
                "ORDER BY r.rolname",
                role["oid"],
            )
            assert not memberships, memberships
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_real_postgres_dual_worker_recovery_and_fencing(monkeypatch):
    tenant_id = str(uuid.uuid4())
    claim_key = f"rib_it_{uuid.uuid4().hex}"
    job_id = f"batch_{uuid.uuid4().hex[:12]}"
    req = _req(tenant_id)

    monkeypatch.setattr(store, "DATABASE_URL", DB_URL)
    monkeypatch.setattr(store, "LEASE_SECONDS", 30)

    async def scenario():
        try:
            first, duplicate = await asyncio.gather(
                store.claim_or_recover(
                    claim_key=claim_key,
                    job_id=job_id,
                    tenant_id=tenant_id,
                    field_id="fld_runtime_cert",
                    req=req,
                    worker_id="worker-a",
                ),
                store.claim_or_recover(
                    claim_key=claim_key,
                    job_id=job_id,
                    tenant_id=tenant_id,
                    field_id="fld_runtime_cert",
                    req=req,
                    worker_id="worker-b",
                ),
            )
            winners = [c for c in (first, duplicate) if c.acquired]
            assert len(winners) == 1
            winner = winners[0]
            assert first.job_id == duplicate.job_id == job_id

            import asyncpg

            conn = await asyncpg.connect(DB_URL, statement_cache_size=0)
            try:
                await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)
                await conn.execute(
                    "UPDATE raster_batch_jobs SET lease_expires_at=now()-interval '1 second' WHERE claim_key=$1",
                    claim_key,
                )
            finally:
                await conn.close()

            recovered = await store.claim_or_recover(
                claim_key=claim_key,
                job_id=job_id,
                tenant_id=tenant_id,
                field_id="fld_runtime_cert",
                req=req,
                worker_id="worker-c",
            )
            assert recovered.acquired and recovered.recovered
            assert recovered.lease_token != winner.lease_token

            stale_finish = await store.finish(
                claim_key=claim_key,
                tenant_id=tenant_id,
                lease_token=winner.lease_token or "",
                status="completed",
                result_payload={"stale": True},
                worker_id=winner.lease_owner,
            )
            assert stale_finish is False

            current_finish = await store.finish(
                claim_key=claim_key,
                tenant_id=tenant_id,
                lease_token=recovered.lease_token or "",
                status="completed",
                result_payload={"ok": True},
                worker_id="worker-c",
            )
            assert current_finish is True

            replay = await store.claim_or_recover(
                claim_key=claim_key,
                job_id=job_id,
                tenant_id=tenant_id,
                field_id="fld_runtime_cert",
                req=req,
                worker_id="worker-d",
            )
            assert replay.acquired is False
            assert replay.status == "completed"
            assert replay.result_payload == {"ok": True}
        finally:
            await _cleanup(claim_key, tenant_id)

    asyncio.run(scenario())


def test_distinct_claim_cannot_reuse_an_existing_job_id(monkeypatch):
    import asyncpg

    tenant_id = str(uuid.uuid4())
    claim_key = f"rib_it_{uuid.uuid4().hex}"
    job_id = f"batch_{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(store, "DATABASE_URL", DB_URL)

    async def scenario():
        kwargs = dict(
            tenant_id=tenant_id,
            job_id=job_id,
            field_id="fld_runtime_cert",
            req=_req(tenant_id),
            worker_id="worker-a",
        )
        try:
            first = await store.claim_or_recover(claim_key=claim_key, **kwargs)
            assert first.acquired
            with pytest.raises(asyncpg.UniqueViolationError) as collision:
                await store.claim_or_recover(claim_key=claim_key + "_other", **kwargs)
            assert collision.value.constraint_name == "raster_batch_jobs_job_id_key"
            replay = await store.claim_or_recover(claim_key=claim_key, **kwargs)
            assert not replay.acquired and replay.job_id == first.job_id
            assert replay.lease_token == first.lease_token
            retry_job_id = f"batch_{uuid.uuid4().hex[:12]}"
            retry = await store.claim_or_recover(
                claim_key=claim_key + "_other", **(kwargs | {"job_id": retry_job_id})
            )
            assert retry.acquired and retry.job_id == retry_job_id
        finally:
            await _cleanup(claim_key, tenant_id)
            await _cleanup(claim_key + "_other", tenant_id)

    asyncio.run(scenario())


@pytest.mark.parametrize("workers", [2, 8])
def test_concurrent_claims_share_one_lease_and_one_attempt(monkeypatch, workers):
    """Separate connections racing for a fresh job must converge without errors."""
    import asyncpg

    tenant_id = str(uuid.uuid4())
    claim_key = f"rib_it_{uuid.uuid4().hex}"
    job_id = f"batch_{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(store, "DATABASE_URL", DB_URL)

    async def scenario():
        barrier = asyncio.Barrier(workers)

        async def connect_together():
            conn = await asyncpg.connect(DB_URL, statement_cache_size=0)
            try:
                await asyncio.wait_for(barrier.wait(), timeout=10)
            except BaseException:
                await conn.close()
                raise
            return conn

        monkeypatch.setattr(store, "_connect", connect_together)
        try:
            claims = await asyncio.wait_for(
                asyncio.gather(
                    *[
                        store.claim_or_recover(
                            claim_key=claim_key,
                            job_id=job_id,
                            tenant_id=tenant_id,
                            field_id="fld_runtime_cert",
                            req=_req(tenant_id),
                            worker_id=f"worker-{index}",
                        )
                        for index in range(workers)
                    ],
                    return_exceptions=True,
                ),
                timeout=20,
            )
            assert all(isinstance(claim, store.DurableClaim) for claim in claims), claims
            assert all(claim.available for claim in claims)
            assert sum(claim.acquired for claim in claims) == 1
            assert {claim.job_id for claim in claims} == {job_id}
            lease_tokens = {claim.lease_token for claim in claims}
            assert len(lease_tokens) == 1 and None not in lease_tokens

            conn = await asyncpg.connect(DB_URL, statement_cache_size=0)
            try:
                await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)
                rows = await conn.fetch(
                    "SELECT job_id, attempt_count, lease_token FROM raster_batch_jobs "
                    "WHERE claim_key=$1",
                    claim_key,
                )
                assert len(rows) == 1
                assert rows[0]["job_id"] == job_id
                assert rows[0]["attempt_count"] == 1
                assert rows[0]["lease_token"] in lease_tokens
            finally:
                await conn.close()
        finally:
            await _cleanup(claim_key, tenant_id)

    asyncio.run(scenario())
