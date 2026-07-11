"""WX-10.10 dispatch-authorization boundary against real Postgres."""

from __future__ import annotations

import asyncio
import json
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
TENANT = "00000000-0000-0000-0000-000000001010"
OTHER = "00000000-0000-0000-0000-000000002010"


def _run(coro):
    return asyncio.run(coro)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


async def _seed(*, state="approved", tenant=TENANT):
    decision_id = "dec_" + uuid4().hex
    review_id = "rev_" + uuid4().hex
    lineage = "lin_" + uuid4().hex
    plan_id = "xplan_" + uuid4().hex
    conn = await _connect()
    try:
        await conn.execute(
            """INSERT INTO decision_record
               (decision_id,tenant_id,decision_type,stage,decision_value,review_state,candidate_lineage_id)
               VALUES ($1,$2::uuid,'crop_decision_candidate','candidate',$3::jsonb,$4,$5)""",
            decision_id,
            tenant,
            json.dumps({"candidate_lineage_id": lineage}),
            state,
            lineage,
        )
        await conn.execute(
            """INSERT INTO decision_reviews
               (review_id,decision_id,tenant_id,action,previous_state,new_state,reason,reviewed_by,
                candidate_lineage_id,idempotency_key,request_hash,policy_version)
               VALUES ($1,$2,$3::uuid,$4,'pending_approval',$5,'ok','reviewer',$6,$7,$8,'p1')""",
            review_id,
            decision_id,
            tenant,
            "approve" if state == "approved" else "reject",
            state,
            lineage,
            "seed-" + uuid4().hex,
            uuid4().hex,
        )
        await conn.execute(
            """INSERT INTO decision_execution_plans
               (execution_plan_id,tenant_id,decision_id,review_id,candidate_lineage_id,
                operation_type,status,idempotency_key,request_hash,created_by)
               VALUES ($1,$2::uuid,$3,$4,$5,'irrigation','planned',$6,$7,'planner')""",
            plan_id,
            tenant,
            decision_id,
            review_id,
            lineage,
            "plan-" + uuid4().hex,
            uuid4().hex,
        )
        return plan_id, decision_id, review_id, lineage
    finally:
        await conn.close()


def _payload(**over):
    values = dict(
        expected_plan_state="planned",
        policy_version="dispatch-policy-v1",
        weather_snapshot_id="wx-snapshot-1",
        resource_snapshot_id="resource-snapshot-1",
        authorization_reason="operator verified",
    )
    values.update(over)
    return SimpleNamespace(**values)


def _authorize(plan_id, decision_id, review_id, lineage, **over):
    from persistence import authorize_dispatch

    args = dict(
        tenant_id=TENANT,
        execution_plan_id=plan_id,
        decision_id=decision_id,
        review_id=review_id,
        candidate_lineage_id=lineage,
        idempotency_key="idem-" + uuid4().hex,
        authorized_by="operations-manager",
        payload=_payload(),
    )
    args.update(over)
    return authorize_dispatch(**args)


def test_planned_approved_source_creates_one_authorization_and_outbox():
    plan, did, rid, lin = _run(_seed())
    res = _run(_authorize(plan, did, rid, lin))
    assert res["status"] == "ok" and res["authorization_state"] == "authorized"
    assert res["authoritative"] is True and res["persisted"] is True

    async def counts():
        conn = await _connect()
        try:
            return (
                await conn.fetchval(
                    "SELECT count(*) FROM decision_dispatch_authorizations WHERE execution_plan_id=$1",
                    plan,
                ),
                await conn.fetchval(
                    """SELECT count(*) FROM decision_outbox_events
                       WHERE event_type='DISPATCH_AUTHORIZATION_CREATED'
                         AND payload->>'execution_plan_id'=$1""",
                    plan,
                ),
            )
        finally:
            await conn.close()

    assert _run(counts()) == (1, 1)


def test_rejected_decision_conflicts():
    plan, did, rid, lin = _run(_seed(state="rejected"))
    assert _run(_authorize(plan, did, rid, lin)) == {
        "status": "conflict",
        "reason": "decision_not_approved",
    }


def test_wrong_tenant_is_not_found_without_oracle():
    plan, did, rid, lin = _run(_seed(tenant=OTHER))
    assert _run(_authorize(plan, did, rid, lin))["status"] == "not_found"


def test_source_identity_mismatches_conflict():
    plan, did, rid, lin = _run(_seed())
    assert _run(_authorize(plan, "wrong", rid, lin))["reason"] == "decision_id_mismatch"
    assert _run(_authorize(plan, did, "wrong", lin))["reason"] == "review_id_mismatch"
    assert _run(_authorize(plan, did, rid, "wrong"))["reason"] == "candidate_lineage_mismatch"


def test_idempotent_replay_and_payload_mismatch():
    plan, did, rid, lin = _run(_seed())
    key = "idem-" + uuid4().hex
    first = _run(_authorize(plan, did, rid, lin, idempotency_key=key))
    replay = _run(_authorize(plan, did, rid, lin, idempotency_key=key))
    assert replay["replay"] is True
    assert replay["dispatch_authorization_id"] == first["dispatch_authorization_id"]
    changed = _payload(weather_snapshot_id="wx-snapshot-2")
    assert _run(_authorize(plan, did, rid, lin, idempotency_key=key, payload=changed)) == {
        "status": "conflict",
        "reason": "idempotency_key_payload_mismatch",
    }


def test_two_concurrent_authorizations_yield_one_record():
    plan, did, rid, lin = _run(_seed())

    async def race():
        from persistence import authorize_dispatch

        common = dict(
            tenant_id=TENANT,
            execution_plan_id=plan,
            decision_id=did,
            review_id=rid,
            candidate_lineage_id=lin,
            authorized_by="operations-manager",
            payload=_payload(),
        )
        return await asyncio.gather(
            authorize_dispatch(idempotency_key="a-" + uuid4().hex, **common),
            authorize_dispatch(idempotency_key="b-" + uuid4().hex, **common),
        )

    results = _run(race())
    assert sum(r["status"] == "ok" for r in results) == 1
    assert sum(r["status"] == "conflict" for r in results) == 1


def test_dispatch_authorization_is_append_only():
    import asyncpg

    plan, did, rid, lin = _run(_seed())
    res = _run(_authorize(plan, did, rid, lin))

    async def mutate(sql):
        conn = await _connect()
        try:
            await conn.execute(sql, res["dispatch_authorization_id"])
        finally:
            await conn.close()

    for sql in (
        "UPDATE decision_dispatch_authorizations SET policy_version='x' WHERE dispatch_authorization_id=$1",
        "DELETE FROM decision_dispatch_authorizations WHERE dispatch_authorization_id=$1",
    ):
        with pytest.raises(asyncpg.PostgresError):
            _run(mutate(sql))
