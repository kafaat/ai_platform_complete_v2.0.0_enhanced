"""WX-12.3 durable runtime schedules: feed emission + reconcile evidence on real Postgres."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres")
TENANT = "00000000-0000-0000-0000-000000009123"


def _run(c):
    return asyncio.run(c)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


async def _seed_schedule(kind: str, model_id: str, period: int = 300, age_seconds: int = 3600):
    """Seed a schedule whose anchor is in the past so windows/periods are already due."""
    sid = "sched_" + uuid4().hex[:20]
    c = await _connect()
    try:
        await c.execute(
            """INSERT INTO decision_model_runtime_schedules(schedule_id,tenant_id,kind,model_id,feature_set_id,target_environment,period_seconds,anchor_at,created_by,idempotency_key,request_hash)
               VALUES($1,$2::uuid,$3,$4,'f1','staging',$5, now() - make_interval(secs => $6),'ops',$7,'h')""",
            sid,
            TENANT,
            kind,
            model_id,
            period,
            age_seconds,
            "idem_" + uuid4().hex,
        )
        return sid
    finally:
        await c.close()


def _iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_monitoring_schedule_emits_due_window_and_snapshot_closes_it():
    from persistence import list_runtime_work, record_monitoring_snapshot

    model = "m_" + uuid4().hex[:8]
    sid = _run(_seed_schedule("monitoring_window", model))
    feed = _run(list_runtime_work(tenant_id=TENANT, worker_id="w1", limit=100))
    item = next(
        (
            i
            for i in feed["items"]
            if i["work_type"] == "monitoring_window" and i["payload"].get("schedule_id") == sid
        ),
        None,
    )
    assert item is not None, "due monitoring window was not emitted"
    p = item["payload"]
    # exact supervisor contract: active_state object + window_start/window_end ISO strings.
    assert p["active_state"]["model_id"] == model
    assert p["active_state"]["target_environment"] == "staging"
    ws, we = _iso(p["window_start"]), _iso(p["window_end"])
    assert (we - ws).total_seconds() == 300

    # recording the snapshot for that exact window removes it from the feed (progression is
    # derived from the append-only evidence, not mutable schedule state).
    snap = SimpleNamespace(
        model_id=model,
        feature_set_id="f1",
        target_environment="staging",
        window_start=ws,
        window_end=we,
        sample_count=10,
        metrics={"feature_drift": 0.0},
        drift_state="stable",
        idempotency_key=f"monitor:{model}:staging:{p['window_start']}:{p['window_end']}",
    )
    res = _run(record_monitoring_snapshot(tenant_id=TENANT, captured_by="adapter-1", payload=snap))
    assert res["status"] == "ok"

    async def _expire():
        c = await _connect()
        try:
            await c.execute(
                "UPDATE decision_model_runtime_work_claims SET lease_expires_at=now()-interval '1 hour' WHERE work_key=$1",
                sid,
            )
        finally:
            await c.close()

    _run(_expire())
    feed2 = _run(list_runtime_work(tenant_id=TENANT, worker_id="w2", limit=100))
    assert not any(i["payload"].get("schedule_id") == sid for i in feed2["items"])


def test_reconcile_schedule_emits_and_evidence_silences_it_for_a_period():
    from persistence import list_runtime_work, record_reconcile_evidence

    model = "m_" + uuid4().hex[:8]
    sid = _run(_seed_schedule("active_state_reconcile", model))
    feed = _run(list_runtime_work(tenant_id=TENANT, worker_id="w1", limit=100))
    item = next(
        (
            i
            for i in feed["items"]
            if i["work_type"] == "active_state_reconcile" and i["payload"].get("schedule_id") == sid
        ),
        None,
    )
    assert item is not None, "due reconcile was not emitted"
    assert isinstance(item["payload"]["period_index"], int)

    key = f"reconcile:{sid}:{item['payload']['period_index']}"
    ev = SimpleNamespace(
        schedule_id=sid,
        model_id=model,
        feature_set_id="f1",
        target_environment="staging",
        expected_artifact_digest="a" * 64,
        observed_artifact_digest="a" * 64,
        drift_detected=False,
        registry_version="1",
        evidence_payload={},
        idempotency_key=key,
    )
    first = _run(record_reconcile_evidence(tenant_id=TENANT, recorded_by="adapter-1", payload=ev))
    assert first["status"] == "ok" and first["drift_detected"] is False
    # identical retry is a replay, not a 409.
    replay = _run(record_reconcile_evidence(tenant_id=TENANT, recorded_by="adapter-1", payload=ev))
    assert replay["status"] == "ok" and replay["replay"] is True

    async def _expire():
        c = await _connect()
        try:
            await c.execute(
                "UPDATE decision_model_runtime_work_claims SET lease_expires_at=now()-interval '1 hour' WHERE work_key=$1",
                sid,
            )
        finally:
            await c.close()

    _run(_expire())
    feed2 = _run(list_runtime_work(tenant_id=TENANT, worker_id="w2", limit=100))
    assert not any(i["payload"].get("schedule_id") == sid for i in feed2["items"]), (
        "reconcile re-emitted despite fresh evidence within the period"
    )


def test_schedule_create_replay_and_conflict():
    from persistence import create_runtime_schedule

    model = "m_" + uuid4().hex[:8]

    def _payload(period: int, key: str):
        return SimpleNamespace(
            kind="monitoring_window",
            model_id=model,
            feature_set_id="f1",
            target_environment="staging",
            period_seconds=period,
            idempotency_key=key,
        )

    key = "sched_" + uuid4().hex
    first = _run(
        create_runtime_schedule(tenant_id=TENANT, created_by="ops", payload=_payload(300, key))
    )
    assert first["status"] == "ok"
    replay = _run(
        create_runtime_schedule(tenant_id=TENANT, created_by="ops", payload=_payload(300, key))
    )
    assert replay["status"] == "ok" and replay["replay"] is True
    conflict = _run(
        create_runtime_schedule(
            tenant_id=TENANT, created_by="ops", payload=_payload(600, "k2_" + uuid4().hex)
        )
    )
    assert conflict["status"] == "conflict"
