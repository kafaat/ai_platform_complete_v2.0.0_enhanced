"""Run both real worker loops with a ready-asset SQL fixture.

Only the DB driver and processing boundary are substituted. The ready query is
executed by SQLite after removing PostgreSQL casts; WHERE/NULL semantics remain
SQL, rather than a mock guessing whether the query mentions a version. This does
not claim PostgreSQL RLS or production persistence coverage.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytestmark = pytest.mark.unit


@pytest.mark.parametrize("mode", ["backfill", "single_scene"])
@pytest.mark.parametrize(
    "stored_version, expected_processed", [("prior/0", True), (None, True), ("canonical/9", False)]
)
def test_ready_requires_the_canonical_processing_version(
    monkeypatch, mode, stored_version, expected_processed
):
    import backfill_scan_worker as worker
    import imagery_product_identity

    monkeypatch.setattr(
        imagery_product_identity, "canonical_processing_version", lambda: "canonical/9"
    )
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE raster_assets (tenant_id TEXT, field_id TEXT, index_name TEXT, scene_id TEXT, acquisition_date TEXT, asset_status TEXT, geometry_revision INTEGER, algorithm_version TEXT)"
    )
    db.execute(
        "INSERT INTO raster_assets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("tenant", "field", "ndvi", "scene", "2026-10-01", "ready", 2, stored_version),
    )
    queries, writes, processed = [], [], []

    class Conn:
        @asynccontextmanager
        async def transaction(self):
            yield self

        async def execute(self, sql, *args):
            writes.append((sql, args))

        async def fetchval(self, sql, *args):
            if sql.startswith("SELECT 1 FROM raster_assets"):
                queries.append((sql, args))
                executable = re.sub(r"::(?:uuid|text|date|int)\b", "", sql)
                executable = re.sub(r"\$(\d+)", r"?\1", executable)
                row = db.execute(executable, args).fetchone()
                return row[0] if row else None
            return "item"

        async def fetch(self, sql, *args):
            return [{"id": "item", "scene_id": "scene", "index_name": "ndvi", "acq": "2026-10-01"}]

    class Pool:
        @asynccontextmanager
        async def acquire(self):
            yield Conn()

    async def search(*args, **kwargs):
        return {
            "items": [{"item_id": "scene", "datetime": "2026-10-01T00:00:00Z", "provider": "cdse"}]
        }

    def process(*args, **kwargs):
        processed.append(args)
        return worker.SceneOutcome(True)

    monkeypatch.setattr(worker.stac_search_helpers, "stac_search", search)
    monkeypatch.setattr(
        worker.scene_policy, "select_backfill_scenes_by_policy", lambda items, **kw: items
    )
    monkeypatch.setattr(worker, "_process_scene_index", process)
    run = {
        "id": "run",
        "tenant_id": "tenant",
        "field_id": "field",
        "geometry_revision": 2,
        "max_cloud_pct": 30,
        "limit_per_month": 2,
        "indices": ["ndvi"],
        "run_kind": mode,
        "clip_polygon_geojson": {
            "type": "Polygon",
            "coordinates": [[[44, 16], [44.01, 16], [44.01, 16.01], [44, 16.01], [44, 16]]],
        },
        "from_date": datetime(2026, 10, 1, tzinfo=UTC),
        "to_date": datetime(2026, 10, 2, tzinfo=UTC),
    }
    try:
        asyncio.run(worker._process_run(Pool(), run))
    finally:
        db.close()
    assert len(queries) == 1
    assert bool(processed) is expected_processed, (
        f"{mode} wrongly reused ready version {stored_version!r}"
    )
    if expected_processed:
        assert len(processed) == 1
    assert any("items_skipped" in sql for sql, _ in writes)
