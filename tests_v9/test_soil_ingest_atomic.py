"""Fault-inject the real soil ingestion/store with a transactional DB adapter.

This checks transaction ownership and rollback, not PostgreSQL's RLS engine.
The companion source-audit probe repeats the scenarios on disposable PostgreSQL.
"""

from __future__ import annotations

import asyncio
import importlib
import secrets
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests_v9.service_module import load_service_main

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TENANT = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(scope="module")
def soil():
    # Several service images export a top-level main/routers package. Keep this
    # service's import graph isolated and restore the previous graph afterwards.
    names = ("main", "router_registry", "routers", "soil_store")
    previous = {
        k: v for k, v in sys.modules.items() if any(k == n or k.startswith(n + ".") for n in names)
    }
    for key in previous:
        del sys.modules[key]
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.syspath_prepend(str(ROOT / "services/soil-service"))
            mp.setenv("DATABASE_URL", "")
            mp.setenv("SAHOOL_AGENT_TOKEN", secrets.token_hex(20))
            main = load_service_main(
                str(ROOT / "services/soil-service"),
                required_attrs=("ingest_reading", "SoilReading", "_REQ_TENANT"),
            )
            yield main, importlib.import_module("soil_store")
    finally:
        for key in list(sys.modules):
            if any(key == n or key.startswith(n + ".") for n in names):
                del sys.modules[key]
        sys.modules.update(previous)


class Transaction:
    def __init__(self, conn):
        self.conn = conn

    async def start(self):
        assert self.conn.pending is None
        self.conn.pending = deepcopy(self.conn.pool.state)

    async def commit(self):
        assert self.conn.pending is not None
        self.conn.pool.state = self.conn.pending
        self.conn.pending = None
        self.conn.tenant = None
        self.conn.pool.commits += 1

    async def rollback(self):
        self.conn.pending = None
        self.conn.tenant = None
        self.conn.pool.rollbacks += 1

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, typ, exc, tb):
        if typ is None:
            await self.commit()
        else:
            await self.rollback()


class Connection:
    def __init__(self, pool):
        self.pool = pool
        self.pending = None
        self.tenant = None

    def transaction(self):
        return Transaction(self)

    @property
    def state(self):
        return self.pending if self.pending is not None else self.pool.state

    def assert_scope(self, tenant):
        if self.pool.strict:
            assert self.pending is not None, "write_outside_transaction"
            assert self.tenant == str(tenant), "write_without_matching_tenant"

    async def execute(self, sql, *args):
        if "set_config" in sql:
            assert self.pending is not None
            self.tenant = args[0]
            if self.pool.failure == "tenant_context":
                raise RuntimeError("tenant_context")
        elif "pg_advisory_xact_lock" in sql:
            assert self.pending is not None
        elif "INSERT INTO soil_readings" in sql:
            self.assert_scope(args[10])
            self.state["legacy"][len(self.state["legacy"]) + 1] = args
        elif "INSERT INTO soil_observations" in sql:
            self.assert_scope(args[2])
            if self.pool.failure == args[5]:
                raise RuntimeError(args[5])
            key = (args[2], args[19])
            if key in self.state["observations"]:
                return "INSERT 0 0"
            self.state["observations"][key] = args
        elif "INSERT INTO soil_profile_projection_jobs" in sql:
            self.assert_scope(args[0])
            if self.pool.failure == "projection_job":
                raise RuntimeError("projection_job")
            self.state["jobs"][(args[0], args[1])] = args
        elif "INSERT INTO soil_profile_current" in sql:
            self.assert_scope(args[0])
            if self.pool.failure == "current_pointer":
                raise RuntimeError("current_pointer")
            self.state["current"][(args[0], args[1])] = args[2]
        return "INSERT 0 1"

    async def fetch(self, sql, *args):
        assert "FROM soil_observations" in sql
        return [
            {
                "observation_id": v[0],
                "tenant_id": v[2],
                "field_id": v[3],
                "property": v[5],
                "value_json": v[6],
                "unit": v[7],
                "depth_from_cm": v[8],
                "depth_to_cm": v[9],
                "observed_at": v[10],
                "received_at": v[11],
                "source_type": v[12],
                "source_id": v[13],
                "quality_status": v[16],
                "quality_flags": v[17],
                "confidence": v[18],
                "idempotency_key": v[19],
                "provenance": v[20],
                "is_superseded": False,
            }
            for v in self.state["observations"].values()
            if v[2] == args[0]
            and (v[19] in args[1] if "ANY($2::text[])" in sql else v[3] == args[1])
        ]

    async def fetchval(self, sql, *args):
        if "INSERT INTO soil_profile_snapshots" in sql:
            self.assert_scope(args[3])
            if self.pool.failure == "snapshot":
                raise RuntimeError("snapshot")
            if args[1] in self.state["snapshots"]:
                return None
            self.state["snapshots"][args[1]] = args[-1]
            return args[-1]
        if "SELECT snapshot" in sql:
            return self.state["snapshots"].get(args[2])
        if "SELECT observation_id" in sql:
            row = self.state["observations"].get((args[0], args[1]))
            if len(args) == 4 and row and (row[3] != args[2] or row[5] != args[3]):
                return None
            return row[0] if row else None
        raise AssertionError(sql)


class Acquire:
    def __init__(self, pool):
        self.conn = Connection(pool)

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *args):
        if self.conn.pending is not None:
            await Transaction(self.conn).rollback()


class Pool:
    def __init__(self, *, failure=None, strict=True):
        self.state = {key: {} for key in ("legacy", "observations", "jobs", "snapshots", "current")}
        self.failure, self.strict = failure, strict
        self.commits = self.rollbacks = self.acquires = 0

    def acquire(self):
        self.acquires += 1
        return Acquire(self)


def ingest(soil, monkeypatch, pool, reading=None):
    main, _store = soil

    async def owner(field_id):
        return TENANT

    monkeypatch.setattr(main, "_pool", pool)
    monkeypatch.setattr(main, "_require_field_tenant", owner)
    reading = reading or main.SoilReading(
        field_id="atomic-field",
        sensor_id="sensor-1",
        temperature=25,
        moisture_pct=30,
        observed_at=datetime(2026, 10, 2, tzinfo=UTC),
        idempotency_key="atomic-1",
    )
    return asyncio.run(main.ingest_reading(reading, x_agent_token=main.AGENT_TOKEN))


def test_all_writes_have_one_matching_tenant_transaction(soil, monkeypatch):
    pool = Pool()
    result = ingest(soil, monkeypatch, pool)
    assert result["status"] == "ingested"
    assert len(pool.state["legacy"]) == 1
    assert len(pool.state["observations"]) == 2
    assert (
        len(pool.state["jobs"]) == len(pool.state["snapshots"]) == len(pool.state["current"]) == 1
    )
    assert pool.acquires == pool.commits == 1
    assert pool.rollbacks == 0


@pytest.mark.parametrize(
    "failure", ["soil_moisture", "projection_job", "snapshot", "current_pointer", "tenant_context"]
)
def test_any_failure_leaves_no_committed_partial_reading(soil, monkeypatch, failure):
    # Disable the adapter's RLS assertion here so the old autocommit path can be
    # measured independently of the missing-context defect.
    pool = Pool(failure=failure, strict=False)
    with pytest.raises(RuntimeError, match=failure):
        ingest(soil, monkeypatch, pool)
    assert all(not rows for rows in pool.state.values()), pool.state
    assert pool.commits == 0
    assert pool.rollbacks == 1


def test_retry_returns_the_persisted_observation_identity(soil, monkeypatch):
    pool = Pool()
    first = ingest(soil, monkeypatch, pool)
    second = ingest(soil, monkeypatch, pool)
    assert second["canonical_observation_ids"] == first["canonical_observation_ids"]
    assert second["profile_id"] == first["profile_id"]
    assert second["profile_hash"] == first["profile_hash"]
    assert len(pool.state["legacy"]) == 1
    assert len(pool.state["observations"]) == 2
    assert len(pool.state["snapshots"]) == 1


def test_a_key_used_for_another_field_cannot_return_its_observations(soil, monkeypatch):
    from fastapi import HTTPException

    main, _store = soil
    pool = Pool()
    ingest(soil, monkeypatch, pool)
    before = deepcopy(pool.state)
    reading = main.SoilReading(
        field_id="another-field",
        sensor_id="sensor-1",
        temperature=25,
        moisture_pct=30,
        observed_at=datetime(2026, 10, 2, tzinfo=UTC),
        idempotency_key="atomic-1",
    )
    with pytest.raises(HTTPException) as failure:
        ingest(soil, monkeypatch, pool, reading)
    assert failure.value.status_code == 409
    assert pool.state == before


def test_cancellation_does_not_leave_an_earlier_write_committed(soil, monkeypatch):
    import projection_jobs

    main, _store = soil
    pool = Pool(strict=False)
    monkeypatch.setattr(main, "_pool", pool)

    async def owner(field_id):
        return TENANT

    monkeypatch.setattr(main, "_require_field_tenant", owner)

    async def run():
        reached = asyncio.Event()

        async def pause(*args, **kwargs):
            reached.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(projection_jobs, "enqueue", pause)
        reading = main.SoilReading(field_id="cancel-field", sensor_id="sensor-1", temperature=25)
        task = asyncio.create_task(main.ingest_reading(reading, x_agent_token=main.AGENT_TOKEN))
        try:
            await asyncio.wait_for(reached.wait(), timeout=1)
            task.cancel()
            outcome = await asyncio.gather(task, return_exceptions=True)
            assert isinstance(outcome[0], asyncio.CancelledError)
            assert all(not rows for rows in pool.state.values())
            assert pool.commits == 0
            assert pool.rollbacks == 1
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())


@pytest.mark.parametrize(
    "changes",
    [
        {"temperature": 26},
        {"moisture_pct": 31},
        {"depth_cm": 40},
        {"sensor_id": "sensor-2"},
        {"observed_at": datetime(2026, 10, 2, 1, tzinfo=UTC)},
        {"ph_level": 7},
        {"temperature": None},
    ],
)
def test_changed_payload_cannot_reuse_a_committed_ingest_key(soil, monkeypatch, changes):
    from fastapi import HTTPException

    main, _store = soil
    pool = Pool()
    ingest(soil, monkeypatch, pool)
    before = deepcopy(pool.state)
    body = dict(
        field_id="atomic-field",
        sensor_id="sensor-1",
        temperature=25,
        moisture_pct=30,
        observed_at=datetime(2026, 10, 2, tzinfo=UTC),
        idempotency_key="atomic-1",
    )
    body.update(changes)
    with pytest.raises(HTTPException) as failure:
        ingest(soil, monkeypatch, pool, main.SoilReading(**body))
    assert failure.value.status_code == 409
    assert pool.state == before


def test_empty_measurement_does_not_create_a_legacy_row_or_profile(soil, monkeypatch):
    from fastapi import HTTPException

    main, _store = soil
    pool = Pool()
    with pytest.raises(HTTPException) as failure:
        ingest(soil, monkeypatch, pool, main.SoilReading(field_id="empty", sensor_id="s"))
    assert failure.value.status_code == 422
    assert pool.acquires == 0
    assert all(not rows for rows in pool.state.values())


def test_a_retry_without_a_client_timestamp_keeps_the_original_ids(soil, monkeypatch):
    main, _store = soil
    pool = Pool()
    body = dict(field_id="atomic-field", sensor_id="s", temperature=25, idempotency_key="key")
    first = ingest(soil, monkeypatch, pool, main.SoilReading(**body))
    second = ingest(soil, monkeypatch, pool, main.SoilReading(**body))
    assert second["canonical_observation_ids"] == first["canonical_observation_ids"]
    assert len(pool.state["legacy"]) == len(pool.state["observations"]) == 1


@pytest.mark.parametrize("key_length", [240, 256])
def test_measurement_key_that_exceeds_the_canonical_limit_is_422(soil, monkeypatch, key_length):
    from fastapi import HTTPException

    main, _store = soil
    pool = Pool()
    reading = main.SoilReading(
        field_id="key-limit", sensor_id="s", temperature=25, idempotency_key="k" * key_length
    )
    with pytest.raises(HTTPException) as failure:
        ingest(soil, monkeypatch, pool, reading)
    assert failure.value.status_code == 422
    assert pool.acquires == 0
    assert all(not rows for rows in pool.state.values())


@pytest.mark.parametrize("measurement,key_length", [("temperature", 239), ("ph_level", 253)])
def test_measurement_key_at_the_canonical_limit_is_accepted(
    soil, monkeypatch, measurement, key_length
):
    main, _store = soil
    pool = Pool()
    body = {"field_id": "key-limit", "sensor_id": "s", "idempotency_key": "k" * key_length}
    body[measurement] = 25 if measurement == "temperature" else 7
    result = ingest(soil, monkeypatch, pool, main.SoilReading(**body))
    assert result["status"] == "ingested"
    assert len(pool.state["observations"]) == 1
    assert len(next(iter(pool.state["observations"]))[1]) == 256
