"""M4-BOOTSTRAP-JOURNAL-CORE-LANDED-DISABLED-01: existing store on PG16.

Use only a disposable local database. Table DDL is read unchanged from init_v8;
no migration is introduced. Production schema presence is not inferred here.
"""

import asyncio
import importlib.util
import os
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from shared.field_bootstrap import LeaseLost, request_key

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.integration


def owner():
    spec = importlib.util.spec_from_file_location(
        "m4_onboarding_owner", ROOT / "services/sahool-platform/api/onboarding.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_real_store_concurrency_rls_lease_and_retry_window():
    from urllib.parse import urlparse

    import asyncpg

    dsn = os.getenv("M4_TEST_DATABASE_URL", "")
    if not dsn:
        if os.getenv("M4_REQUIRE_PG16") == "1":
            pytest.fail("M4_REQUIRE_PG16=1 requires M4_TEST_DATABASE_URL")
        pytest.skip("BLOCKED_BY_ENVIRONMENT: no disposable PG16 configured")
    assert urlparse(dsn).hostname in ("127.0.0.1", "localhost", "::1"), "local disposable PG only"
    admin = await asyncpg.connect(dsn)
    suffix = uuid4().hex
    schema, role = "m4_" + suffix, "m4_role_" + suffix
    tenant, other = str(uuid4()), str(uuid4())
    model = owner()
    try:
        assert 160000 <= int(await admin.fetchval("SHOW server_version_num")) < 170000
        await admin.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        await admin.execute(f'CREATE ROLE "{role}" NOSUPERUSER NOBYPASSRLS NOLOGIN')
        await admin.execute(f'SET search_path TO "{schema}", public')
        source = (ROOT / "migrations/init_v8.sql").read_text(encoding="utf-8")
        ddl = re.search(r"CREATE TABLE IF NOT EXISTS processing_jobs \(.*?\n\);", source, re.S)
        assert ddl, "existing processing_jobs DDL missing: blocked, do not invent table"
        await admin.execute(ddl.group())
        await admin.execute(
            "ALTER TABLE processing_jobs ENABLE ROW LEVEL SECURITY; ALTER TABLE processing_jobs FORCE ROW LEVEL SECURITY"
        )
        policy = re.search(
            r"CREATE POLICY tenant_isolation ON %I\s+USING \(.*?\n\s*\)", source, re.S
        )
        assert policy, "existing tenant policy missing"
        await admin.execute(policy.group().replace("%I", "processing_jobs"))
        await admin.execute(
            f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"; GRANT SELECT,INSERT,UPDATE ON processing_jobs TO "{role}"; GRANT USAGE ON SEQUENCE processing_jobs_id_seq TO "{role}"'
        )

        @asynccontextmanager
        async def connection(for_tenant=tenant):
            conn = await asyncpg.connect(dsn)
            try:
                async with conn.transaction():
                    await conn.execute(f'SET LOCAL ROLE "{role}"')
                    await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
                    await conn.execute(
                        "SELECT set_config('app.current_tenant',$1,true)", for_tenant
                    )
                    flags = await conn.fetchrow(
                        "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
                    )
                    assert not flags["rolsuper"] and not flags["rolbypassrls"]
                    yield conn
            finally:
                await conn.close()

        geometry = {"type": "Polygon", "coordinates": [[[44, 15], [45, 15], [45, 16], [44, 15]]]}

        async def enqueue(conn, when=datetime(2024, 2, 29, tzinfo=UTC)):
            return await model.enqueue_field_bootstrap(
                conn, tenant_id=tenant, field_id="m4-field", geometry=geometry, created_at=when
            )

        # Observe the actual advisory lock wait before committing the first insert.
        waiting = asyncio.Event()

        async def competitor():
            async with connection() as conn:
                pid = conn.get_server_pid()
                waiting.pid = pid
                waiting.set()
                return await enqueue(conn)

        async with connection() as first:
            job = await enqueue(first)
            task = asyncio.create_task(competitor())
            await waiting.wait()

            async def lock_wait():
                for _ in range(500):
                    if await admin.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=$1 AND locktype='advisory' AND NOT granted)",
                        waiting.pid,
                    ):
                        return
                    await asyncio.sleep(0.01)
                pytest.fail("second worker did not wait for advisory lock")

            await asyncio.wait_for(lock_wait(), 6)
        assert await asyncio.wait_for(task, 5) == job
        store = model.PlatformBootstrapStore(connection, tenant_id=tenant)
        # Separate transactions: locked row is skipped, not blocked.
        async with connection() as first:
            await first.fetchrow("SELECT id FROM processing_jobs WHERE id=$1 FOR UPDATE", job)
            assert await asyncio.wait_for(store.claim(job), 2) is None
        claimed = await store.claim(job)
        assert claimed is not None
        assert await store.claim(job) is None
        async with connection(other) as outsider:
            assert await outsider.fetchval("SELECT count(*) FROM processing_jobs") == 0
            assert (
                await outsider.fetchval(
                    "UPDATE processing_jobs SET status='failed' WHERE id=$1 RETURNING id", job
                )
                is None
            )
        other_store = model.PlatformBootstrapStore(lambda: connection(other), tenant_id=other)
        assert await other_store.claim(job) is None
        with pytest.raises(LeaseLost):
            await store.checkpoint(job, str(uuid4()), claimed.journal)
        await store.checkpoint(job, claimed.token, claimed.journal)
        # Expire via owner fixture; all store calls still use the restricted role.
        await admin.execute(
            "UPDATE processing_jobs SET result=jsonb_set(result,'{lease,expires_at}',to_jsonb((clock_timestamp()-interval '1 second')::text)) WHERE id=$1",
            job,
        )
        with pytest.raises(LeaseLost):
            await store.finish(job, claimed.token, claimed.journal)
        retried = await store.claim(job)
        assert retried.token != claimed.token
        assert retried.journal["scope"] == claimed.journal["scope"]
        assert retried.journal["scope"]["start_date"] == "2022-02-28"
        assert retried.journal["scope"]["end_date"] == "2024-02-28"
        assert request_key(retried.journal, "weather_history") == request_key(
            claimed.journal, "weather_history"
        )
        with pytest.raises(LeaseLost):
            await store.finish(job, claimed.token, claimed.journal)
        await store.finish(job, retried.token, retried.journal)
    finally:
        await admin.execute("RESET search_path")
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.execute(f'DROP ROLE IF EXISTS "{role}"')
        await admin.close()
