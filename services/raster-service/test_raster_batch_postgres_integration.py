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
