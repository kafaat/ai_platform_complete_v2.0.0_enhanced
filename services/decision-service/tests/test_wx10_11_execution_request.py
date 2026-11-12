"""WX-10.11a execution-request boundary against real Postgres."""

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
TENANT = "00000000-0000-0000-0000-000000001111"


def _run(c):
    return asyncio.run(c)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


async def _seed(field_id=None, resources=None):
    did = "dec_" + uuid4().hex
    rid = "rev_" + uuid4().hex
    lin = "lin_" + uuid4().hex
    pid = "xplan_" + uuid4().hex
    aid = "dauth_" + uuid4().hex
    c = await _connect()
    try:
        await c.execute(
            "INSERT INTO decision_record(decision_id,tenant_id,decision_type,stage,decision_value,review_state,candidate_lineage_id,field_id) VALUES($1,$2::uuid,'candidate','candidate',$3::jsonb,'approved',$4,$5)",
            did,
            TENANT,
            json.dumps({"candidate_lineage_id": lin}),
            lin,
            field_id,
        )
        await c.execute(
            "INSERT INTO decision_reviews(review_id,decision_id,tenant_id,action,previous_state,new_state,reason,reviewed_by,candidate_lineage_id,idempotency_key,request_hash,policy_version) VALUES($1,$2,$3::uuid,'approve','pending_approval','approved','ok','r',$4,$5,$6,'p1')",
            rid,
            did,
            TENANT,
            lin,
            "r-" + uuid4().hex,
            uuid4().hex,
        )
        await c.execute(
            "INSERT INTO decision_execution_plans(execution_plan_id,tenant_id,decision_id,review_id,candidate_lineage_id,operation_type,status,idempotency_key,request_hash,created_by,required_resources) VALUES($1,$2::uuid,$3,$4,$5,'irrigation','planned',$6,$7,'p',$8::jsonb)",
            pid,
            TENANT,
            did,
            rid,
            lin,
            "p-" + uuid4().hex,
            uuid4().hex,
            json.dumps(resources or []),
        )
        await c.execute(
            "INSERT INTO decision_dispatch_authorizations(dispatch_authorization_id,tenant_id,execution_plan_id,decision_id,review_id,candidate_lineage_id,expected_plan_state,status,policy_version,weather_snapshot_id,resource_snapshot_id,authorization_reason,idempotency_key,request_hash,authorized_by) VALUES($1,$2::uuid,$3,$4,$5,$6,'planned','authorized','p1','w1','r1','ok',$7,$8,'m')",
            aid,
            TENANT,
            pid,
            did,
            rid,
            lin,
            "a-" + uuid4().hex,
            uuid4().hex,
        )
        return aid, pid, did
    finally:
        await c.close()


def _payload(aid, pid, did, key=None):
    return SimpleNamespace(
        dispatch_authorization_id=aid,
        execution_plan_id=pid,
        decision_id=did,
        target_type="task",
        target_id="task-provider",
        operation_type="irrigation",
        command_payload={"minutes": 20},
        idempotency_key=key or "e-" + uuid4().hex,
    )


def test_create_execution_request_and_outbox():
    from persistence import create_execution_request

    aid, pid, did = _run(_seed())
    res = _run(
        create_execution_request(
            tenant_id=TENANT,
            dispatch_authorization_id=aid,
            requested_by="operator",
            payload=_payload(aid, pid, did),
        )
    )
    assert res["status"] == "ok" and res["execution_state"] == "queued"

    async def counts():
        c = await _connect()
        try:
            return await c.fetchval(
                "SELECT count(*) FROM decision_execution_requests WHERE execution_request_id=$1",
                res["execution_request_id"],
            ), await c.fetchval(
                "SELECT count(*) FROM decision_outbox_events WHERE event_type='EXECUTION_REQUEST_CREATED' AND aggregate_id=$1",
                res["execution_request_id"],
            )
        finally:
            await c.close()

    assert _run(counts()) == (1, 1)


def test_equipment_request_uses_field_and_device_from_the_approved_chain():
    from persistence import create_execution_request

    async def exercise():
        aid, pid, did = await _seed("pivot", [{"device_id": "test-valve"}])
        c = await _connect()
        try:
            p = _payload(aid, pid, did)
            p.target_type, p.target_id = "equipment", "test-valve"
            p.command_payload = {
                "device_id": "test-valve",
                "command": "open_valve",
                "payload": {"field_id": "east", "duration_sec": 60},
            }

            async def submit():
                return await create_execution_request(
                    tenant_id=TENANT,
                    dispatch_authorization_id=aid,
                    requested_by="operator",
                    payload=p,
                )

            rejected = await submit()
            assert rejected["reason"] == "command_field_mismatch"
            assert (
                await c.fetchval(
                    "SELECT count(*) FROM decision_execution_requests WHERE decision_id=$1", did
                )
                == 0
            )
            p.command_payload["payload"]["field_id"] = "pivot"
            accepted = await submit()
            assert accepted["execution_state"] == "queued"
            assert (
                await c.fetchval(
                    "SELECT count(*) FROM decision_outbox_events WHERE aggregate_id=$1",
                    accepted["execution_request_id"],
                )
                == 1
            )
        finally:
            await c.close()

    _run(exercise())
