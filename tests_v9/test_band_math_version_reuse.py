"""A ready asset computed under an older band-math version is not reused.

`sahool.band_math/2` changed the output of a normalized-difference pixel whose two bands
are both 0 (a valid 0.0 under /1, no-data now). Both preflights that decide "this product
is already ready, skip it" must therefore refuse a /1 asset, or the old output is served
as current forever:

- the bulk backfill worker (`backfill_scan_worker._ready_asset`);
- the single-scene enqueue (`db_persist.enqueue_single_scene_process`).

The fake connection below evaluates the ready-asset query against an in-memory table and
filters on the algorithm version **only when the query itself names the column**, reading
the parameter position from the SQL text. A preflight that drops the version clause
therefore matches the /1 row and the test fails.
"""

from __future__ import annotations

import asyncio
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RASTER = ROOT / "services" / "raster-service"
if str(RASTER) not in sys.path:
    sys.path.insert(0, str(RASTER))

import imagery_product_identity as identity_mod  # noqa: E402
import raster_quality  # noqa: E402

TENANT = "11111111-1111-4111-8111-111111111111"
FIELD = "field-1"
SCENE = "S2A_MSIL2A_20261001T073609_N0511_R092_T38PNA"
DAY = "2026-10-01"


def _asset(version: str | None) -> dict:
    return {
        "tenant_id": TENANT,
        "field_id": FIELD,
        "index_name": "ndvi",
        "scene_id": SCENE,
        "acquisition_date": DAY,
        "asset_status": "ready",
        "geometry_revision": 3,
        "algorithm_version": version,
    }


def _version_param(query: str) -> int | None:
    match = re.search(r"algorithm_version\s*=\s*\$(\d+)", query)
    return int(match.group(1)) - 1 if match else None


class _Conn:
    """Answers the ready-asset preflight from `assets`; records every statement."""

    def __init__(self, assets: list[dict]):
        self.assets = assets
        self.statements: list[tuple[str, tuple]] = []
        self.existing_lookup_args: tuple | None = None

    async def fetchval(self, query: str, *args):
        self.statements.append((query, args))
        if "FROM raster_assets" not in query:
            return None
        position = _version_param(query)
        for row in self.assets:
            if row["asset_status"] != "ready" or row["scene_id"] != SCENE:
                continue
            if position is not None and row["algorithm_version"] != args[position]:
                continue
            return 1
        return None

    async def fetchrow(self, query: str, *args):
        self.statements.append((query, args))
        if "FROM backfill_run_items" in query:
            self.existing_lookup_args = args
            # A live item for this key: the enqueue answers "in_progress" without a new run.
            return {"id": 7, "run_id": 3, "status": "queued", "error": None}
        return None

    async def execute(self, query: str, *args):
        self.statements.append((query, args))
        return "OK"

    @asynccontextmanager
    async def _tx(self):
        yield self

    def transaction(self):
        return self._tx()

    async def close(self):
        return None


def test_the_canonical_version_is_band_math_2_and_the_fallback_agrees():
    assert raster_quality.ALGORITHM_VERSION == "sahool.band_math/2"
    assert identity_mod.canonical_processing_version() == "sahool.band_math/2"
    # The import-failure fallback must name the current version, not the old one.
    saved = sys.modules.get("raster_quality")
    sys.modules["raster_quality"] = None  # type: ignore[assignment]
    try:
        assert identity_mod.canonical_processing_version() == raster_quality.ALGORITHM_VERSION
    finally:
        sys.modules["raster_quality"] = saved


def test_legacy_items_are_reused_only_at_the_baseline_version_not_the_current_one():
    def _id(version: str):
        return identity_mod.ImageryProductIdentity.create(
            tenant_id=TENANT,
            field_id=FIELD,
            geometry_revision=3,
            provider="cdse",
            scene_id=SCENE,
            product="ndvi",
            processing_version=version,
        )

    # Version-less legacy items were computed under /1. A /2 identity must not adopt them.
    assert identity_mod.LEGACY_BASELINE_PROCESSING_VERSION == "sahool.band_math/1"
    assert _id(identity_mod.canonical_processing_version()).legacy_matches_baseline() is False
    assert _id("sahool.band_math/1").legacy_matches_baseline() is True


def _worker_ready(assets: list[dict]):
    import backfill_scan_worker as worker

    conn = _Conn(assets)
    found = asyncio.run(
        worker._ready_asset(
            conn,
            tenant=TENANT,
            field=FIELD,
            index="ndvi",
            scene={"item_id": SCENE},
            scene_id=SCENE,
            acq=DAY,
            geom_rev=3,
            proc_ver=identity_mod.canonical_processing_version(),
            native=None,
        )
    )
    return found, conn


def test_backfill_worker_treats_a_band_math_1_asset_as_stale():
    found, conn = _worker_ready([_asset("sahool.band_math/1")])
    assert found is None, "a ready /1 asset must not satisfy the /2 preflight"
    query, args = conn.statements[-1]
    position = _version_param(query)
    assert position is not None and args[position] == "sahool.band_math/2"


def test_backfill_worker_still_skips_a_current_version_asset():
    found, _ = _worker_ready([_asset("sahool.band_math/2")])
    assert found == 1


def test_backfill_worker_treats_a_version_less_asset_as_stale():
    found, _ = _worker_ready([_asset(None)])
    assert found is None


def _enqueue(monkeypatch, assets: list[dict]):
    import db_persist

    conn = _Conn(assets)

    async def _connect():
        return conn

    monkeypatch.setattr(db_persist, "_connect", _connect)
    result = asyncio.run(
        db_persist.enqueue_single_scene_process(
            tenant_id=TENANT,
            field_id=FIELD,
            acquisition_date=DAY,
            index_name="ndvi",
            scene_id=SCENE,
            geometry_revision=3,
        )
    )
    return result, conn


def test_single_scene_enqueue_does_not_answer_already_ready_from_a_band_math_1_asset(monkeypatch):
    result, conn = _enqueue(monkeypatch, [_asset("sahool.band_math/1")])
    assert result is not None
    assert result["status"] != "already_ready", result
    # It went on to the item lookup, keyed by the /2 identity.
    assert conn.existing_lookup_args is not None
    assert conn.existing_lookup_args[1].endswith(":sahool.band_math/2")
    # And no version-less legacy item was re-keyed onto the /2 identity.
    assert not any("UPDATE backfill_run_items" in q for q, _ in conn.statements)


def test_single_scene_enqueue_still_answers_already_ready_for_a_current_asset(monkeypatch):
    result, _ = _enqueue(monkeypatch, [_asset("sahool.band_math/2")])
    assert result is not None and result["status"] == "already_ready"
