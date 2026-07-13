"""P6 live PostgreSQL failure-mode certification; runs in the integration CI job."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

asyncpg = pytest.importorskip("asyncpg")
pytestmark = pytest.mark.integration
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)


async def connect():
    try:
        return await asyncpg.connect(DSN, statement_cache_size=0)
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}")


async def test_p6_tables_force_rls_and_with_check():
    c = await connect()
    try:
        names = ["soil_runtime_certification_runs", "soil_runtime_certification_evidence"]
        rows = await c.fetch(
            "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=ANY($1::text[])",
            names,
        )
        assert {r["relname"] for r in rows} == set(names)
        assert all(r["relrowsecurity"] and r["relforcerowsecurity"] for r in rows)
        policies = await c.fetch(
            "SELECT tablename,qual,with_check FROM pg_policies WHERE schemaname='public' AND tablename=ANY($1::text[])",
            names,
        )
        assert len(policies) == 2 and all(
            "app.current_tenant" in (r["qual"] or "")
            and "app.current_tenant" in (r["with_check"] or "")
            for r in policies
        )
    finally:
        await c.close()


async def test_expired_projection_lease_is_reclaimed_and_dead_letter_persists():
    c = await connect()
    tenant = str(uuid.uuid4())
    field = f"fld_p6_{uuid.uuid4().hex[:10]}"
    try:
        jid = await c.fetchval(
            "INSERT INTO soil_profile_projection_jobs(tenant_id,field_id,status,attempts,lease_owner,lease_expires_at) VALUES($1::uuid,$2,'running',1,'dead-worker',NOW()-interval '5 minutes') RETURNING job_id",
            tenant,
            field,
        )
        row = await c.fetchrow(
            "SELECT * FROM sahool_claim_soil_projection_job('recovery-worker',30)"
        )
        assert row and row["job_id"] == jid and row["attempts"] == 2
        await c.execute(
            "SELECT sahool_finish_soil_projection_job($1,'dead_letter',0,'injected permanent failure')",
            jid,
        )
        state = await c.fetchrow(
            "SELECT status,lease_owner,lease_expires_at,last_error FROM soil_profile_projection_jobs WHERE job_id=$1",
            jid,
        )
        assert (
            state["status"] == "dead_letter"
            and state["lease_owner"] is None
            and state["lease_expires_at"] is None
        )
        assert "injected permanent failure" in state["last_error"]
    finally:
        await c.execute("DELETE FROM soil_profile_projection_jobs WHERE tenant_id=$1::uuid", tenant)
        await c.close()


async def test_concurrent_supersession_accepts_one_replacement():
    c = await connect()
    tenant = str(uuid.uuid4())
    field = f"fld_p6_sup_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)

    async def obs(conn, oid, key, val):
        await conn.execute(
            "INSERT INTO soil_observations(observation_id,contract_version,tenant_id,field_id,property,value_json,depth_from_cm,depth_to_cm,observed_at,received_at,source_type,source_id,quality_status,confidence,idempotency_key,provenance) VALUES($1,'soil-observation.v1',$2::uuid,$3,'ph',to_jsonb($4::float8),0,30,$5,$5,'lab','p6','accepted',.95,$6,'{}')",
            oid,
            tenant,
            field,
            val,
            now,
            key,
        )

    old = "obs_" + uuid.uuid4().hex
    replacements = ["obs_" + uuid.uuid4().hex for _ in range(2)]
    try:
        await obs(c, old, "old", 7.0)
        for i, r in enumerate(replacements):
            await obs(c, r, f"r{i}", 7.1 + i)

        async def link(rep):
            x = await asyncpg.connect(DSN, statement_cache_size=0)
            try:
                await x.execute(
                    "INSERT INTO soil_observation_supersessions(tenant_id,superseded_observation_id,replacement_observation_id,reason) VALUES($1::uuid,$2,$3,'correction')",
                    tenant,
                    old,
                    rep,
                )
                return True
            except asyncpg.UniqueViolationError:
                return False
            finally:
                await x.close()

        accepted = await asyncio.gather(*(link(r) for r in replacements))
        assert sum(accepted) == 1
    finally:
        await c.execute(
            "DELETE FROM soil_observation_supersessions WHERE tenant_id=$1::uuid", tenant
        )
        await c.execute("DELETE FROM soil_observations WHERE tenant_id=$1::uuid", tenant)
        await c.close()
