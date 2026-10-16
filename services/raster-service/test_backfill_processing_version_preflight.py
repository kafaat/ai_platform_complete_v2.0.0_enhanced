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
            "items": [
                {
                    "item_id": "scene",
                    "datetime": "2026-10-01T00:00:00Z",
                    "provider": "element84",
                    "bands_urls": {"red": "red.tif"},
                }
            ]
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


@pytest.mark.parametrize("mode", ["backfill", "single_scene"])
@pytest.mark.parametrize("conflict", [False, True])
@pytest.mark.parametrize(
    "changed",
    [
        None,
        "request",
        "algorithm",
        "mask",
        "geometry",
        "tenant",
        "scene",
        "cog",
        "job",
        "unknown",
        "local_processing",
        "field",
        "request_geometry",
        "catalogue_alias",
    ],
)
def test_native_ready_reuses_only_current_request_product(monkeypatch, mode, conflict, changed):
    import json

    import backfill_scan_worker as worker
    import cdse_client
    import cdse_native_product as native
    from imagery_product_identity import canonical_processing_version

    clip = {
        "type": "Polygon",
        "coordinates": [[[44, 16], [44.01, 16], [44.01, 16.01], [44, 16.01], [44, 16]]],
    }
    scene = {"item_id": "catalogue-scene", "datetime": "2026-10-01T00:00:00Z", "provider": "cdse"}
    digest, algorithm = cdse_client.backfill_request_identity(scene, "ndvi", clip)
    receipt = {
        "request_sha256": digest,
        "scene_id": "cdse:sh:123",
        "acquisition_datetime": "2026-10-01T07:30:00+00:00",
        "input_checksum": "a" * 64,
        "algorithm_version": algorithm,
        "qa_mask_version": native.MASK_VERSION,
        "native_valid_pixels": 90,
        "local_processing_version": canonical_processing_version(),
    }
    row = {
        "tenant_id": "tenant",
        "field_id": "field",
        "index_name": "ndvi",
        "scene_id": "cdse:sh:123",
        "acquisition_date": "2026-10-01",
        "asset_status": "ready",
        "geometry_revision": 2,
        "algorithm_version": algorithm,
        "qa_mask_version": native.MASK_VERSION,
        "processing_job_id": "prior-job",
        "cog_uri": "s3://bucket/current-cog",
    }
    provenance = {"current_cog_uri": row["cog_uri"], "stats": {"cdse_native_qa": receipt}}
    if changed == "request":
        receipt["request_sha256"] = "old-request"
    elif changed == "algorithm":
        row["algorithm_version"] = "old-algorithm"
    elif changed == "mask":
        row["qa_mask_version"] = "old-mask"
    elif changed == "geometry":
        row["geometry_revision"] = 1
    elif changed == "tenant":
        row["tenant_id"] = "other-tenant"
    elif changed == "scene":
        row["scene_id"] = "catalogue-scene"
    elif changed == "cog":
        row["cog_uri"] = "s3://bucket/replaced-cog"
    elif changed == "job":
        row["processing_job_id"] = None
    elif changed == "unknown":
        provenance = {}
    elif changed == "local_processing":
        receipt["local_processing_version"] = "prior-local-processor"
    elif changed == "field":
        row["field_id"] = "other-field"
    elif changed == "request_geometry":
        clip["coordinates"][0][1][0] = 44.005
    elif changed == "catalogue_alias":
        scene["provider"] = "copernicus"
    row["provenance"] = json.dumps(provenance)
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE raster_assets (tenant_id TEXT, field_id TEXT, index_name TEXT, scene_id TEXT, acquisition_date TEXT, asset_status TEXT, geometry_revision INTEGER, algorithm_version TEXT, qa_mask_version TEXT, processing_job_id TEXT, cog_uri TEXT, provenance TEXT)"
    )
    db.execute("INSERT INTO raster_assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", tuple(row.values()))
    processed, queries = [], []

    class Conn:
        @asynccontextmanager
        async def transaction(self):
            yield self

        async def execute(self, sql, *args):
            pass

        async def fetchval(self, sql, *args):
            if sql.startswith("SELECT 1 FROM raster_assets"):
                queries.append(sql)
                executable = re.sub(
                    r"provenance #>> '\{([^}]+)\}'",
                    lambda m: "json_extract(provenance, '$." + m[1].replace(",", ".") + "')",
                    sql,
                )
                executable = re.sub(
                    r"\((json_extract\(provenance, '\$\.stats\.cdse_native_qa\.acquisition_datetime'\))\)::text::date",
                    r"substr(\1,1,10)",
                    executable,
                )
                executable = re.sub(r"::(?:uuid|text|date|int)\b", "", executable)
                executable = re.sub(r"\$(\d+)", r"?\1", executable)
                result = db.execute(executable, args).fetchone()
                return result[0] if result else None
            if "INSERT INTO backfill_run_items" in sql and conflict:
                return None
            return "item"

        async def fetch(self, sql, *args):
            return [
                {
                    "id": "item",
                    "scene_id": "catalogue-scene",
                    "index_name": "ndvi",
                    "acq": "2026-10-01",
                }
            ]

    class Pool:
        @asynccontextmanager
        async def acquire(self):
            yield Conn()

    async def search(*args, **kwargs):
        return {"items": [scene]}

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
        "clip_polygon_geojson": clip,
        "from_date": datetime(2026, 10, 1, tzinfo=UTC),
        "to_date": datetime(2026, 10, 2, tzinfo=UTC),
    }
    try:
        asyncio.run(worker._process_run(Pool(), run))
    finally:
        db.close()
    assert len(queries) == 1
    assert len(processed) == (0 if changed in (None, "catalogue_alias") else 1)
