"""WX-12.1 runtime work-feed + rollout/retraining dispatch receipts against real Postgres."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres")
TENANT = "00000000-0000-0000-0000-000000009121"


def _run(c):
    return asyncio.run(c)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


async def _seed_retraining() -> str:
    """Runtime cohort lineage: a retraining request must inherit from a monitoring snapshot,
    which itself must reference the latest 'activated' receipt — seed the honest chain."""
    from _model_chain import seed_activated_model

    rid = "retrain_" + uuid4().hex
    model = "m_" + uuid4().hex[:8]
    c = await _connect()
    try:
        ids = await seed_activated_model(c, tenant=TENANT, model_id=model)
        mid = "monitor_" + uuid4().hex[:20]
        await c.execute(
            """INSERT INTO decision_model_monitoring_snapshots
               (monitoring_snapshot_id,tenant_id,model_id,feature_set_id,target_environment,
                window_start,window_end,sample_count,metrics,drift_state,source_receipt_id,
                captured_by,idempotency_key,request_hash)
               VALUES($1,$2::uuid,$3,'f1','staging',now()-interval '1 hour',now(),10,
                      '{}'::jsonb,'warning',$4,'adapter-test',$5,'h')""",
            mid,
            TENANT,
            model,
            ids["activation_receipt_id"],
            "idem_" + uuid4().hex,
        )
        await c.execute(
            """INSERT INTO decision_model_retraining_requests(retraining_request_id,tenant_id,model_id,feature_set_id,target_environment,source_monitoring_snapshot_id,dataset_fingerprint,training_manifest,code_version,hyperparameters,requested_by,idempotency_key,request_hash)
               VALUES($1,$2::uuid,$3,'f1','staging',$4,$5,'{"a":1}'::jsonb,'v1','{"lr":0.1}'::jsonb,'planner',$6,'h')""",
            rid,
            TENANT,
            model,
            mid,
            "a" * 64,
            "idem_" + uuid4().hex,
        )
        return rid
    finally:
        await c.close()


async def _seed_rollout_plan() -> str:
    """A rollout plan must reference a real 'activated' receipt (cohort lineage trigger)."""
    from _model_chain import seed_activated_model

    pid = "rollout_" + uuid4().hex
    c = await _connect()
    try:
        ids = await seed_activated_model(c, tenant=TENANT, model_id="m_" + uuid4().hex[:8])
        await c.execute(
            """INSERT INTO decision_model_rollout_plans(rollout_plan_id,tenant_id,activation_receipt_id,mode,traffic_percent,policy,requested_by,idempotency_key,request_hash)
               VALUES($1,$2::uuid,$3,'canary',10,'{}'::jsonb,'planner',$4,'h')""",
            pid,
            TENANT,
            ids["activation_receipt_id"],
            "idem_" + uuid4().hex,
        )
        return pid
    finally:
        await c.close()


def _rollout_payload(key: str, state: str = "applied") -> SimpleNamespace:
    return SimpleNamespace(
        receipt_state=state,
        controller_id="adapter-1",
        observed_traffic_percent=10.0,
        candidate_artifact_digest="d" * 64,
        routing_version="v1",
        failure_reason=None if state == "applied" else "boom",
        receipt_payload={},
        idempotency_key=key,
    )


def _dispatch_payload(key: str, state: str = "dispatched") -> SimpleNamespace:
    return SimpleNamespace(
        dispatch_state=state,
        dispatcher_id="adapter-1",
        job_id="job-1" if state == "dispatched" else None,
        backend="b1",
        failure_reason=None if state == "dispatched" else "boom",
        receipt_payload={},
        idempotency_key=key,
    )


def test_runtime_work_feed_surfaces_retraining_dispatch_with_full_payload():
    from persistence import list_runtime_work, record_retraining_dispatch_receipt

    rid = _run(_seed_retraining())
    feed = _run(list_runtime_work(tenant_id=TENANT, worker_id="w1", limit=50))
    item = next(
        (
            i
            for i in feed["items"]
            if i["work_type"] == "retraining_dispatch"
            and i["payload"]["retraining_request_id"] == rid
        ),
        None,
    )
    assert item is not None
    # the feed must carry every key the training-backend helper consumes.
    for k in (
        "model_id",
        "feature_set_id",
        "dataset_fingerprint",
        "training_manifest",
        "code_version",
        "hyperparameters",
    ):
        assert k in item["payload"], k

    res = _run(
        record_retraining_dispatch_receipt(
            tenant_id=TENANT,
            recorded_by="adapter-1",
            retraining_request_id=rid,
            payload=_dispatch_payload("disp_" + rid),
        )
    )
    assert res["status"] == "ok"
    # once acknowledged, the item leaves the feed.
    feed2 = _run(list_runtime_work(tenant_id=TENANT, worker_id="w1", limit=50))
    assert not any(i["payload"].get("retraining_request_id") == rid for i in feed2["items"])


def test_dispatch_receipt_replay_vs_conflict_and_guards_missing_request():
    from persistence import record_retraining_dispatch_receipt

    rid = _run(_seed_retraining())
    key = "disp_" + rid
    first = _run(
        record_retraining_dispatch_receipt(
            tenant_id=TENANT,
            recorded_by="a",
            retraining_request_id=rid,
            payload=_dispatch_payload(key),
        )
    )
    assert first["status"] == "ok" and not first.get("replay")
    # identical retry (same request) is a safe replay, not a 409.
    replay = _run(
        record_retraining_dispatch_receipt(
            tenant_id=TENANT,
            recorded_by="a",
            retraining_request_id=rid,
            payload=_dispatch_payload(key),
        )
    )
    assert replay["status"] == "ok" and replay["replay"] is True
    assert replay["dispatch_receipt_id"] == first["dispatch_receipt_id"]
    # a genuinely different payload for the same request is a real conflict.
    conflict = _run(
        record_retraining_dispatch_receipt(
            tenant_id=TENANT,
            recorded_by="a",
            retraining_request_id=rid,
            payload=_dispatch_payload("k_" + uuid4().hex, state="dispatch_failed"),
        )
    )
    assert conflict["status"] == "conflict"
    missing = _run(
        record_retraining_dispatch_receipt(
            tenant_id=TENANT,
            recorded_by="a",
            retraining_request_id="retrain_" + uuid4().hex,
            payload=_dispatch_payload("k_" + uuid4().hex),
        )
    )
    assert missing["status"] == "not_found"


async def _expire_claim(work_key: str) -> None:
    c = await _connect()
    try:
        await c.execute(
            "UPDATE decision_model_runtime_work_claims SET lease_expires_at=now()-interval '1 hour' WHERE work_key=$1 AND work_type='retraining_dispatch'",
            work_key,
        )
    finally:
        await c.close()


def test_runtime_work_claim_is_single_owner_and_reclaimable_on_expiry():
    from persistence import list_runtime_work

    rid = _run(_seed_retraining())
    f1 = _run(list_runtime_work(tenant_id=TENANT, worker_id="w1", limit=100))
    assert any(i["payload"].get("retraining_request_id") == rid for i in f1["items"])
    # a second replica must NOT receive the same item while w1 holds a live lease.
    f2 = _run(list_runtime_work(tenant_id=TENANT, worker_id="w2", limit=100))
    assert not any(i["payload"].get("retraining_request_id") == rid for i in f2["items"])
    # once the lease expires, the item is reclaimable by another replica.
    _run(_expire_claim(rid))
    f3 = _run(list_runtime_work(tenant_id=TENANT, worker_id="w2", limit=100))
    assert any(i["payload"].get("retraining_request_id") == rid for i in f3["items"])


def test_rollout_receipt_persists_append_only_and_guards_missing_plan():
    from persistence import record_rollout_receipt

    pid = _run(_seed_rollout_plan())
    key = "roll_" + pid
    first = _run(
        record_rollout_receipt(
            tenant_id=TENANT,
            recorded_by="adapter-1",
            rollout_plan_id=pid,
            payload=_rollout_payload(key),
        )
    )
    assert first["status"] == "ok" and first["receipt_state"] == "applied"

    async def count():
        c = await _connect()
        try:
            return await c.fetchval(
                "SELECT count(*) FROM decision_model_rollout_receipts WHERE rollout_plan_id=$1", pid
            )
        finally:
            await c.close()

    assert _run(count()) == 1
    replay = _run(
        record_rollout_receipt(
            tenant_id=TENANT,
            recorded_by="adapter-1",
            rollout_plan_id=pid,
            payload=_rollout_payload(key),
        )
    )
    assert replay["status"] == "ok" and replay["replay"] is True
    assert _run(count()) == 1  # replay did not write a second row
    missing = _run(
        record_rollout_receipt(
            tenant_id=TENANT,
            recorded_by="adapter-1",
            rollout_plan_id="rollout_" + uuid4().hex,
            payload=_rollout_payload("k_" + uuid4().hex),
        )
    )
    assert missing["status"] == "not_found"


def test_work_feed_empty_is_valid_sql():
    from persistence import list_runtime_work

    feed = _run(list_runtime_work(tenant_id="00000000-0000-0000-0000-0000000099ff", worker_id="w1"))
    assert feed["status"] == "ok" and feed["items"] == []
