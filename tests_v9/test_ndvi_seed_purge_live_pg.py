"""W1-21 (remote-2 / data-7) — v283 purges the tenant-less RANDOM() NDVI seed, live PG.

``init_v8.sql`` seeds ``ndvi_timeseries`` with 30 days of ``RANDOM()`` values per demo field and
no ``tenant_id``; the table has no live writer, so that invented series was all NL-GIS and decision
confidence could read. The readers now use raster-service; v283 deletes the seed. Measured on the
schema the full manifest produced:

1. after the manifest (which runs init_v8's seed, then v283) no tenant-less row is left;
2. v283 deletes tenant-less rows and only those: rows that carry a tenant survive, exactly;
   negative control: the tenant-less rows are present right before v283 runs;
3. v283 is idempotent: a second run deletes nothing and fails nothing;
4. a role subject to RLS (FORCE RLS hides the tenant-less rows) is refused loudly instead of
   deleting nothing while claiming the purge;
5. the rollback restores no synthetic row (documented in the .down.sql) and only clears the
   table comment; v283 re-applied afterwards leaves the database as it found it.

Run: ``TEST_DATABASE_ADMIN_URL=… pytest -m integration <this file>``.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import os
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

_CERTIFICATION_REQUIRED = os.getenv("NDVI_SEED_PURGE_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
except ImportError:
    if _CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg", reason="asyncpg is not installed")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
if not _ADMIN_DSN and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        "NDVI_SEED_PURGE_CERTIFICATION_REQUIRED=1 without TEST_DATABASE_ADMIN_URL: the job "
        "claims a certification with no database to certify on."
    )
pytestmark.append(
    pytest.mark.skipif(not _ADMIN_DSN, reason="needs TEST_DATABASE_ADMIN_URL (migrated live DB)")
)

_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
_UP = (_MIGRATIONS / "v283_ndvi_timeseries_seed_purge.sql").read_text(encoding="utf-8")
_DOWN = (_MIGRATIONS / "v283_ndvi_timeseries_seed_purge.down.sql").read_text(encoding="utf-8")


def _run(body):
    async def wrapper():
        conn = await asyncpg.connect(_ADMIN_DSN)
        try:
            await body(conn)
        finally:
            await conn.close()

    asyncio.run(wrapper())


async def _insert(conn, field_id: str, tenant: str | None, days: int) -> None:
    today = _dt.date.today()
    for d in range(days):
        await conn.execute(
            "INSERT INTO ndvi_timeseries (field_id, acquisition_date, ndvi_mean, tenant_id)"
            " VALUES ($1, $2, 0.5, $3::uuid)",
            field_id,
            today - _dt.timedelta(days=d),
            tenant,
        )


async def _count(conn, field_id: str) -> int:
    return await conn.fetchval("SELECT count(*) FROM ndvi_timeseries WHERE field_id = $1", field_id)


def test_the_manifest_leaves_no_tenantless_seed_row():
    async def body(conn):
        left = await conn.fetchval("SELECT count(*) FROM ndvi_timeseries WHERE tenant_id IS NULL")
        assert left == 0, f"{left} tenant-less (RANDOM() seed) rows survive the full manifest"
        comment = await conn.fetchval("SELECT obj_description('ndvi_timeseries'::regclass)")
        assert comment and "v283" in comment, f"v283 did not run on this schema: {comment!r}"

    _run(body)


def test_v280_deletes_tenantless_rows_only_and_is_idempotent():
    tag = uuid.uuid4().hex[:10]
    seed_field, owned_field = f"w121-seed-{tag}", f"w121-owned-{tag}"
    tenant = str(uuid.uuid4())

    async def body(conn):
        try:
            await _insert(conn, seed_field, None, 3)
            await _insert(conn, owned_field, tenant, 2)
            # Negative control: the tenant-less rows exist until v283 runs.
            assert await _count(conn, seed_field) == 3, "setup: tenant-less rows were not inserted"

            await conn.execute(_UP)
            assert await _count(conn, seed_field) == 0, "v283 left tenant-less rows in place"
            assert await _count(conn, owned_field) == 2, "v283 deleted rows that carry a tenant"
            others = await conn.fetchval(
                "SELECT count(*) FROM ndvi_timeseries WHERE tenant_id IS NULL"
            )
            assert others == 0, f"{others} tenant-less rows remain after v283"

            await conn.execute(_UP)  # second run: no error, nothing more deleted
            assert await _count(conn, owned_field) == 2, "a second v283 run deleted tenant rows"
        finally:
            await conn.execute(
                "DELETE FROM ndvi_timeseries WHERE field_id = ANY($1::text[])",
                [seed_field, owned_field],
            )

    _run(body)


def test_v280_refuses_a_role_subject_to_rls_instead_of_deleting_nothing():
    """FORCE RLS hides tenant-less rows from a non-bypass role: v283 must fail, not "succeed"."""
    tag = uuid.uuid4().hex[:10]
    seed_field = f"w121-rls-{tag}"
    role = f"w121_rls_{tag}"

    async def body(conn):
        await conn.execute(f'CREATE ROLE "{role}" NOSUPERUSER NOBYPASSRLS NOLOGIN')
        try:
            await conn.execute(f'GRANT SELECT, DELETE ON ndvi_timeseries TO "{role}"')
            await _insert(conn, seed_field, None, 1)
            before = await conn.fetchval("SELECT obj_description('ndvi_timeseries'::regclass)")
            await conn.execute(f'SET ROLE "{role}"')
            try:
                with pytest.raises(asyncpg.PostgresError, match="subject to RLS"):
                    await conn.execute(_UP)
            finally:
                await conn.execute("ROLLBACK")
                await conn.execute("RESET ROLE")
            assert await _count(conn, seed_field) == 1, (
                "setup/negative control: the refused run must leave the tenant-less row in place"
            )
            after = await conn.fetchval("SELECT obj_description('ndvi_timeseries'::regclass)")
            assert after == before, f"a refused v283 run still changed the comment: {after!r}"
        finally:
            await conn.execute("DELETE FROM ndvi_timeseries WHERE field_id = $1", seed_field)
            await conn.execute(f'REVOKE ALL ON ndvi_timeseries FROM "{role}"')
            await conn.execute(f'DROP ROLE IF EXISTS "{role}"')

    _run(body)


def test_rollback_restores_no_synthetic_row():
    tag = uuid.uuid4().hex[:10]
    owned_field = f"w121-down-{tag}"

    async def body(conn):
        try:
            await _insert(conn, owned_field, str(uuid.uuid4()), 1)
            await conn.execute(_DOWN)
            left = await conn.fetchval(
                "SELECT count(*) FROM ndvi_timeseries WHERE tenant_id IS NULL"
            )
            assert left == 0, f"the rollback re-created {left} synthetic seed rows"
            assert await _count(conn, owned_field) == 1, "the rollback touched a tenant's row"
            comment = await conn.fetchval("SELECT obj_description('ndvi_timeseries'::regclass)")
            assert comment is None, f"the rollback left v283's table comment: {comment!r}"
        finally:
            await conn.execute(_UP)  # put the schema back as the manifest left it
            await conn.execute("DELETE FROM ndvi_timeseries WHERE field_id = $1", owned_field)
        comment = await conn.fetchval("SELECT obj_description('ndvi_timeseries'::regclass)")
        assert comment and "v283" in comment, "v283 re-applied after the rollback did not restore"

    _run(body)
