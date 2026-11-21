"""P1-2 (real Postgres): concurrent single-scene enqueues must not leave an orphan run.

Two/eight concurrent enqueue_single_scene_process calls for the SAME product identity converge on
exactly ONE run_item and leave ZERO `planned` single_scene runs without items (the loser of the
ON CONFLICT race must delete the run it just created before returning the winner's item).

CI runs this against the migrated database as the restricted application role.
Local runs without RASTER_TEST_DATABASE_URL skip the integration test.
Run locally with: RASTER_TEST_DATABASE_URL=postgresql://... pytest test_single_scene_concurrent_pg.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

DB_URL = os.getenv("RASTER_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DB_URL, reason="RASTER_TEST_DATABASE_URL is not configured")

FIELD = "fld-p12-concurrent"
DATE = "2026-05-01"
SCENE = "S2_P12_CONCURRENT_0001"
INDEX = "ndvi"


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB_URL, statement_cache_size=0, timeout=5, command_timeout=10)


async def _cleanup(tenant_id: str) -> None:
    conn = await _connect()
    try:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)
        await conn.execute(
            "DELETE FROM backfill_run_items WHERE tenant_id=$1::uuid AND field_id=$2",
            tenant_id,
            FIELD,
        )
        await conn.execute(
            "DELETE FROM backfill_runs WHERE tenant_id=$1::uuid AND field_id=$2", tenant_id, FIELD
        )
    finally:
        await conn.close()


@pytest.mark.parametrize("workers", [2, 8])
def test_concurrent_enqueue_leaves_one_item_and_no_orphan_run(monkeypatch, workers) -> None:
    import asyncpg
    import db_persist

    monkeypatch.setattr(db_persist, "DATABASE_URL", DB_URL)
    tenant_id = str(uuid.uuid4())

    async def _run():
        preflight_barrier = asyncio.Barrier(workers)
        preflight_connections = set()
        created_runs = []
        item_attempts = []
        deletions = []

        class ObservedConnection:
            """Observe real SQL results; synchronize only the empty-item preflight."""

            def __init__(self, conn):
                self._conn = conn

            def __getattr__(self, name):
                return getattr(self._conn, name)

            async def fetchrow(self, query, *args, **kwargs):
                row = await self._conn.fetchrow(query, *args, **kwargs)
                if " ".join(query.split()).startswith(
                    "SELECT id, run_id, status, error FROM backfill_run_items "
                ):
                    assert row is None, "every worker must observe the initially absent item"
                    preflight_connections.add(self._conn.get_server_pid())
                    # No worker may insert a run/item before every worker's SELECT
                    # has returned None. The late-reader reuse branch cannot satisfy
                    # this test: every loser must reach ON CONFLICT DO NOTHING.
                    await asyncio.wait_for(preflight_barrier.wait(), timeout=10)
                return row

            async def fetchval(self, query, *args, **kwargs):
                value = await self._conn.fetchval(query, *args, **kwargs)
                statement = " ".join(query.split())
                if statement.startswith("INSERT INTO backfill_runs (") and value is not None:
                    created_runs.append(int(value))
                elif statement.startswith("INSERT INTO backfill_run_items ("):
                    item_attempts.append((int(args[0]), value))
                return value

            async def execute(self, query, *args, **kwargs):
                result = await self._conn.execute(query, *args, **kwargs)
                if " ".join(query.split()).startswith(
                    "DELETE FROM backfill_runs WHERE id=$1 AND run_kind='single_scene' "
                ):
                    deletions.append((int(args[0]), result))
                return result

        async def observed_connect():
            conn = await asyncpg.connect(
                DB_URL, statement_cache_size=0, timeout=5, command_timeout=20
            )
            return ObservedConnection(conn)

        monkeypatch.setattr(db_persist, "_connect", observed_connect)
        common = dict(
            tenant_id=tenant_id,
            field_id=FIELD,
            acquisition_date=DATE,
            index_name=INDEX,
            scene_id=SCENE,
            geometry_revision=1,
            clip_polygon_geojson=None,
        )
        results = await asyncio.wait_for(
            asyncio.gather(
                *[db_persist.enqueue_single_scene_process(**common) for _ in range(workers)],
                return_exceptions=True,
            ),
            timeout=30,
        )
        assert all(isinstance(result, dict) for result in results), results
        assert len(preflight_connections) == workers, preflight_connections
        assert len(created_runs) == len(set(created_runs)) == workers, created_runs
        assert len(item_attempts) == workers, item_attempts
        assert {run_id for run_id, _ in item_attempts} == set(created_runs), item_attempts
        winner_runs = {run_id for run_id, item_id in item_attempts if item_id is not None}
        loser_runs = {run_id for run_id, item_id in item_attempts if item_id is None}
        assert len(winner_runs) == 1, item_attempts
        assert len(loser_runs) == workers - 1, item_attempts
        assert len(deletions) == workers - 1, deletions
        assert {run_id for run_id, _ in deletions} == loser_runs, deletions
        assert all(result == "DELETE 1" for _, result in deletions), deletions

        conn = await _connect()
        try:
            await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)
            items = await conn.fetchval(
                "SELECT count(*) FROM backfill_run_items WHERE tenant_id=$1::uuid "
                "AND field_id=$2 AND scene_id=$3",
                tenant_id,
                FIELD,
                SCENE,
            )
            orphan_runs = await conn.fetchval(
                "SELECT count(*) FROM backfill_runs r WHERE r.tenant_id=$1::uuid AND r.field_id=$2 "
                "AND r.run_kind='single_scene' "
                "AND NOT EXISTS (SELECT 1 FROM backfill_run_items i WHERE i.run_id=r.id)",
                tenant_id,
                FIELD,
            )
            surviving_runs = await conn.fetch(
                "SELECT id FROM backfill_runs WHERE tenant_id=$1::uuid AND field_id=$2 "
                "AND run_kind='single_scene'",
                tenant_id,
                FIELD,
            )
        finally:
            await conn.close()
        assert {row["id"] for row in surviving_runs} == winner_runs, surviving_runs
        assert {result["run_id"] for result in results} == winner_runs, results
        assert sum(result["status"] == "planned" for result in results) == 1, results
        assert sum(result["status"] == "in_progress" for result in results) == workers - 1, results
        return results, items, orphan_runs

    try:
        results, items, orphan_runs = asyncio.run(_run())
        assert all(r is not None for r in results), results
        assert items == 1, f"expected exactly one canonical run_item, got {items}"
        assert orphan_runs == 0, f"expected zero orphan single_scene runs, got {orphan_runs}"
        # All callers converge on the same item id.
        assert all(r.get("item_id") is not None for r in results), results
        assert len({r["item_id"] for r in results}) == 1, results
    finally:

        async def cleanup_with_timeout():
            await asyncio.wait_for(_cleanup(tenant_id), timeout=10)

        asyncio.run(cleanup_with_timeout())
