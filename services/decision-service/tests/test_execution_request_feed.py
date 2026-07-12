"""ACTUATOR-DISPATCH-CONSUMER — the governed physical-delivery chain on real Postgres.

Proves the P0 closure from the 2026-07-12 consumers audit end-to-end at the
decision-service boundary: a queued equipment request appears on the discovery
feed, disappears once claimed (in-flight), and reaches a terminal accepted state
after the adapter receipt — approved decision → plan → authorization → request →
claim → receipt. Mirror mode is a fail-closed 503, never an empty feed.
"""

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
TENANT = "00000000-0000-0000-0000-000000009201"


def _run(c):
    return asyncio.run(c)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


async def _seed_authorized_chain():
    """approved decision → plan → dispatch authorization (the governed prerequisites)."""
    did, rid, lin = "dec_" + uuid4().hex, "rev_" + uuid4().hex, "lin_" + uuid4().hex
    pid, aid = "xplan_" + uuid4().hex, "dauth_" + uuid4().hex
    c = await _connect()
    try:
        await c.execute(
            "INSERT INTO decision_record(decision_id,tenant_id,decision_type,stage,decision_value,review_state,candidate_lineage_id) VALUES($1,$2::uuid,'candidate','candidate',$3::jsonb,'approved',$4)",
            did,
            TENANT,
            json.dumps({"candidate_lineage_id": lin}),
            lin,
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
            "INSERT INTO decision_execution_plans(execution_plan_id,tenant_id,decision_id,review_id,candidate_lineage_id,operation_type,status,idempotency_key,request_hash,created_by) VALUES($1,$2::uuid,$3,$4,$5,'irrigation','planned',$6,$7,'p')",
            pid,
            TENANT,
            did,
            rid,
            lin,
            "p-" + uuid4().hex,
            uuid4().hex,
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


def _queue_equipment_request(aid: str, pid: str, did: str) -> str:
    from persistence import create_execution_request

    res = _run(
        create_execution_request(
            tenant_id=TENANT,
            dispatch_authorization_id=aid,
            requested_by="operator",
            payload=SimpleNamespace(
                dispatch_authorization_id=aid,
                execution_plan_id=pid,
                decision_id=did,
                target_type="equipment",
                target_id="valve-7",
                operation_type="irrigation",
                command_payload={"device_id": "valve-7", "command": "open", "risk_level": "low"},
                idempotency_key="e-" + uuid4().hex,
            ),
        )
    )
    assert res["status"] == "ok" and res["execution_state"] == "queued", res
    return res["execution_request_id"]


def test_feed_claim_receipt_full_chain():
    from persistence import (
        claim_execution_request,
        list_queued_execution_requests,
        record_execution_receipt,
    )

    aid, pid, did = _run(_seed_authorized_chain())
    req_id = _queue_equipment_request(aid, pid, did)

    # (1) الطلب المصفوف يظهر على feed الاكتشاف بحمولته الكاملة.
    feed = _run(list_queued_execution_requests(tenant_id=TENANT, target_type="equipment"))
    assert feed["authoritative"] is True and feed["read_only"] is True
    mine = [i for i in feed["items"] if i["execution_request_id"] == req_id]
    assert len(mine) == 1
    assert mine[0]["target_id"] == "valve-7"
    assert mine[0]["command_payload"]["command"] == "open"
    assert mine[0]["decision_id"] == did

    # (2) المطالبة الذرّيّة تسحبه من الـfeed (قيد التسليم — لا adapter ثانٍ يراه).
    token = uuid4().hex
    claim = _run(
        claim_execution_request(
            tenant_id=TENANT,
            execution_request_id=req_id,
            adapter_id="actuator-service",
            adapter_kind="equipment",
            delivery_token=token,
        )
    )
    assert claim["status"] == "ok", claim
    feed_after = _run(list_queued_execution_requests(tenant_id=TENANT, target_type="equipment"))
    assert not [i for i in feed_after["items"] if i["execution_request_id"] == req_id]

    # (3) إيصال الـadapter يُنهي الطلب accepted — السلسلة كاملة قرار→تسليم مُثبَتة.
    receipt = _run(
        record_execution_receipt(
            tenant_id=TENANT,
            execution_request_id=req_id,
            adapter_id="actuator-service",
            delivery_token=token,
            receipt_id="rcpt_" + uuid4().hex[:12],
            receipt_status="accepted",
            receipt_payload={"published": True, "device_id": "valve-7"},
        )
    )
    assert receipt["status"] == "ok", receipt

    async def final_state():
        c = await _connect()
        try:
            return await c.fetchval(
                "SELECT status FROM decision_execution_requests WHERE execution_request_id=$1",
                req_id,
            )
        finally:
            await c.close()

    assert _run(final_state()) == "accepted"


def test_feed_filters_and_tenant_isolation():
    from persistence import list_queued_execution_requests

    aid, pid, did = _run(_seed_authorized_chain())
    req_id = _queue_equipment_request(aid, pid, did)

    # فلتر task لا يعيد طلب equipment.
    tasks = _run(list_queued_execution_requests(tenant_id=TENANT, target_type="task"))
    assert not [i for i in tasks["items"] if i["execution_request_id"] == req_id]

    # مستأجر آخر لا يرى الطلب إطلاقاً.
    other = _run(
        list_queued_execution_requests(
            tenant_id="00000000-0000-0000-0000-000000009202", target_type="equipment"
        )
    )
    assert not [i for i in other["items"] if i["execution_request_id"] == req_id]


def test_http_feed_contract_queued_only_and_mirror_503(monkeypatch):
    import importlib.util

    from fastapi.testclient import TestClient

    spec = importlib.util.spec_from_file_location("decision_feed_main", SERVICE_DIR / "main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    client = TestClient(mod.app)

    ok = client.get(
        "/v1/execution-requests",
        params={"state": "queued", "target_type": "equipment"},
        headers={"X-Tenant-Id": TENANT},
    )
    assert ok.status_code == 200 and ok.json()["read_only"] is True

    not_a_feed = client.get(
        "/v1/execution-requests", params={"state": "accepted"}, headers={"X-Tenant-Id": TENANT}
    )
    assert not_a_feed.status_code == 422

    monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "false")
    mirror = client.get("/v1/execution-requests", headers={"X-Tenant-Id": TENANT})
    assert mirror.status_code == 503
