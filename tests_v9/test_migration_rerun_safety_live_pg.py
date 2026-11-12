"""Every deploy re-applies the whole MANIFEST to a database that already holds data.

``migrations/apply_in_compose.sh`` keeps no ledger: all files run on every deploy, so each one
must be a no-op on a populated, already-migrated schema. A fresh chain on an empty database
(what every other job measures) cannot see four defects that broke this:

* v183 re-ran its backfill UPDATEs and v182's trigger rejected them (deploy aborts once one
  recommendation row exists);
* v9 re-created tenant_isolation in its permissive form, so a deploy aborted between v9 and
  v206 left every table writable without a tenant (fail-open WITH CHECK);
* v145 re-ran its product dedup on the narrower pre-v154 key, deleting legitimate reprocesses
  (same scene, new algorithm version) and re-creating the index that forbids them;
* v51 narrowed events_entity_type_check back to 11 values, which fails once an event row
  holds a newer category such as ``harvest_lot``.

This test seeds one row per case, re-applies the MANIFEST with the CI apply script, then
re-runs the RLS files alone (an aborted deploy), and checks that the data and the policies
are unchanged. It must run after the other live tests in the job: it re-applies the schema
and leaves its seed rows (events are append-only).

Runs in "Live PG Proofs" (``SAHOOL_REQUIRE_LIVE_PG=1``: absent database = failure, not skip).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

# It re-applies the whole MANIFEST to the database it reaches, so it runs only where that is the
# point: the Live PG Proofs job (SAHOOL_REQUIRE_LIVE_PG=1), never against a database found by
# accident under ``-m integration``.
pytestmark = [pytest.mark.integration, pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[1]
_REQUIRE = os.environ.get("SAHOOL_REQUIRE_LIVE_PG") == "1"
TENANT = "7e57a11d-0000-4000-8000-00000000c0de"
SCENE = f"RERUN_{uuid.uuid4().hex[:8]}"
REC_ID = f"rerun-{uuid.uuid4().hex[:8]}"
# What an aborted deploy re-runs before it reaches v206.
RLS_FILES = (
    "v9_rls_tenant_isolation.sql",
    "v56_rls_dynamic_all.sql",
    "v70_rls_with_check_propagate.sql",
)

_POLICY_FINGERPRINT = """
SELECT md5(string_agg(
    concat_ws('|', tablename, policyname, permissive, cmd, roles::text, qual, with_check),
    E'\\n' ORDER BY tablename, policyname))
FROM pg_policies WHERE schemaname = 'public'
"""


def _conn_args() -> dict:
    return {
        "host": os.environ.get("SAHOOL_TEST_PGHOST", "/var/run/postgresql"),
        "port": os.environ.get("SAHOOL_TEST_PGPORT", "5432"),
        "database": os.environ.get("SAHOOL_TEST_PGDATABASE", "sahool"),
        "user": os.environ.get("SAHOOL_TEST_PGOWNER", "sahool_user"),
    }


async def _connect():
    import asyncpg

    a = _conn_args()
    return await asyncpg.connect(
        host=a["host"],
        port=int(a["port"]),
        database=a["database"],
        user=a["user"],
        password=os.environ.get("PGPASSWORD"),
        timeout=10,
    )


def _reachable() -> bool:
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        return False

    async def ping():
        await (await _connect()).close()

    try:
        asyncio.run(ping())
        return True
    except Exception:  # noqa: BLE001 - any failure means "no database here"
        return False


async def _seed() -> None:
    conn = await _connect()
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", TENANT)
            # C1: one recommendation with a content digest.
            await conn.execute(
                "INSERT INTO recommendations(rec_id, tenant_id, content_digest) VALUES ($1, $2::uuid, 'x')",
                REC_ID,
                TENANT,
            )
            # C3: the same scene processed by two algorithm versions (two v154 identities).
            for version in ("algo.v1", "algo.v2"):
                await conn.execute(
                    """INSERT INTO raster_assets(field_id, tenant_id, scene_id, acquisition_date,
                           index_name, cog_uri, algorithm_version, product_identity_key)
                       VALUES ('rerun_field', $1::uuid, $2, DATE '2026-06-01', 'ndvi', $3, $4, $5)""",
                    TENANT,
                    SCENE,
                    f"s3://rerun/{SCENE}/{version}.tif",
                    version,
                    f"rip_rerun_{SCENE}_{version}",
                )
            # R-C1: an event in a category v51 does not list.
            await conn.execute(
                """SELECT emit_event('harvest.lot.created', 'harvest_lot', $1, $2::uuid,
                                     '{}'::jsonb, 'system', NULL, NULL, now())""",
                REC_ID,
                TENANT,
            )
    finally:
        await conn.close()


async def _observe() -> dict:
    conn = await _connect()
    try:
        return {
            "policies": await conn.fetchval(_POLICY_FINGERPRINT),
            "recommendation": await conn.fetchval(
                "SELECT count(*) FROM recommendations WHERE rec_id = $1", REC_ID
            ),
            "raster_versions": sorted(
                r["algorithm_version"]
                for r in await conn.fetch(
                    "SELECT algorithm_version FROM raster_assets WHERE scene_id = $1", SCENE
                )
            ),
            "harvest_lot_events": await conn.fetchval(
                "SELECT count(*) FROM events WHERE entity_type = 'harvest_lot' AND entity_id = $1",
                REC_ID,
            ),
            "narrow_product_index": await conn.fetchval(
                "SELECT count(*) FROM pg_indexes WHERE indexname = 'uq_raster_assets_product'"
            ),
        }
    finally:
        await conn.close()


def _env() -> dict:
    env = dict(os.environ)
    env.setdefault("PGPASSWORD", "")
    return env


def _reapply_manifest() -> subprocess.CompletedProcess:
    a = _conn_args()
    return subprocess.run(
        [
            "bash",
            "scripts/ci/apply_migration_manifest.sh",
            "--host",
            a["host"],
            "--port",
            a["port"],
            "--user",
            a["user"],
            "--db",
            a["database"],
        ],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=1200,
    )


def _apply_file(name: str) -> subprocess.CompletedProcess:
    a = _conn_args()
    return subprocess.run(
        [
            "psql",
            "-h",
            a["host"],
            "-p",
            a["port"],
            "-U",
            a["user"],
            "-d",
            a["database"],
            "-v",
            "ON_ERROR_STOP=1",
            "-q",
            "-f",
            f"migrations/{name}",
        ],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )


@pytest.fixture(scope="module")
def seeded():
    if not _REQUIRE:
        pytest.skip("re-applies the MANIFEST: runs only with SAHOOL_REQUIRE_LIVE_PG=1")
    if not _reachable():
        if _REQUIRE:
            pytest.fail("SAHOOL_REQUIRE_LIVE_PG=1 but the database is unreachable")
        pytest.skip("no live Postgres (set SAHOOL_REQUIRE_LIVE_PG=1 to make this a failure)")
    if shutil.which("psql") is None:
        pytest.fail("psql is required to re-apply the MANIFEST")
    asyncio.run(_seed())
    before = asyncio.run(_observe())
    # The seed must be what the cases need, or the checks below would pass vacuously.
    assert before["recommendation"] == 1
    assert before["raster_versions"] == ["algo.v1", "algo.v2"]
    assert before["harvest_lot_events"] == 1
    return before


@pytest.fixture(scope="module")
def after_full_rerun(seeded):
    result = _reapply_manifest()
    lines = (result.stdout + result.stderr).splitlines()
    tail = "\n".join([ln for ln in lines if "ERROR" in ln or "::error" in ln][:10] or lines[-15:])
    assert result.returncode == 0, (
        f"re-applying the MANIFEST on a populated database failed:\n{tail}"
    )
    return asyncio.run(_observe())


def test_full_rerun_keeps_reprocessed_raster_products(after_full_rerun):
    assert after_full_rerun["raster_versions"] == ["algo.v1", "algo.v2"]
    assert after_full_rerun["narrow_product_index"] == 0


def test_full_rerun_keeps_recommendations_and_events(after_full_rerun):
    assert after_full_rerun["recommendation"] == 1
    assert after_full_rerun["harvest_lot_events"] == 1


def test_full_rerun_leaves_every_policy_unchanged(seeded, after_full_rerun):
    assert after_full_rerun["policies"] == seeded["policies"]


def test_aborted_deploy_rls_files_alone_leave_every_policy_unchanged(seeded, after_full_rerun):
    for name in RLS_FILES:
        result = _apply_file(name)
        assert result.returncode == 0, f"{name}: {result.stderr[-2000:]}"
    after = asyncio.run(_observe())
    assert after["policies"] == seeded["policies"], (
        "re-running the RLS migrations without v206 changed tenant_isolation policies "
        "(an aborted deploy would leave them in that state)"
    )
