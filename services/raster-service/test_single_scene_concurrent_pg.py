"""P1-2 (real Postgres): concurrent single-scene enqueues must not leave an orphan run.

Two concurrent enqueue_single_scene_process calls for the SAME product identity must converge on
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

    return await asyncpg.connect(DB_URL, statement_cache_size=0)


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


def test_concurrent_enqueue_leaves_one_item_and_no_orphan_run(monkeypatch) -> None:
    import db_persist

    monkeypatch.setattr(db_persist, "DATABASE_URL", DB_URL)
    tenant_id = str(uuid.uuid4())

    async def _run():
        common = dict(
            tenant_id=tenant_id,
            field_id=FIELD,
            acquisition_date=DATE,
            index_name=INDEX,
            scene_id=SCENE,
            geometry_revision=1,
            clip_polygon_geojson=None,
        )
        # Two concurrent enqueues for the identical product identity (separate connections).
        results = await asyncio.gather(
            db_persist.enqueue_single_scene_process(**common),
            db_persist.enqueue_single_scene_process(**common),
        )
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
        finally:
            await conn.close()
        return results, items, orphan_runs

    try:
        results, items, orphan_runs = asyncio.run(_run())
        assert all(r is not None for r in results), results
        assert items == 1, f"expected exactly one canonical run_item, got {items}"
        assert orphan_runs == 0, f"expected zero orphan single_scene runs, got {orphan_runs}"
        # Both callers converge on the same item id.
        item_ids = {r.get("item_id") for r in results if r.get("item_id") is not None}
        assert len(item_ids) == 1, item_ids
    finally:
        asyncio.run(_cleanup(tenant_id))
