"""WX-10.11b delivery claim and terminal receipt against real Postgres."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres")
TENANT = "00000000-0000-0000-0000-000000001112"
OTHER = "00000000-0000-0000-0000-000000001113"


def _run(c):
    return asyncio.run(c)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


async def _seed(target="task", tenant=TENANT):
    rid = "exec_" + uuid4().hex
    c = await _connect()
    try:
        await c.execute(
            """INSERT INTO decision_execution_requests(execution_request_id,tenant_id,dispatch_authorization_id,execution_plan_id,decision_id,target_type,target_id,operation_type,command_payload,status,idempotency_key,request_hash,requested_by) VALUES($1,$2::uuid,$3,$4,$5,$6,'target','irrigation','{}'::jsonb,'queued',$7,$8,'operator')""",
            rid,
            tenant,
            "auth_" + uuid4().hex,
            "plan_" + uuid4().hex,
            "dec_" + uuid4().hex,
            target,
            "i-" + uuid4().hex,
            uuid4().hex,
        )
        return rid
    finally:
        await c.close()


def test_claim_then_accepted_receipt_and_outbox():
    from persistence import claim_execution_request, record_execution_receipt

    rid = _run(_seed())
    token = "tok-" + uuid4().hex
    claim = _run(
        claim_execution_request(
            tenant_id=TENANT,
            execution_request_id=rid,
            adapter_id="task-adapter",
            adapter_kind="task",
            delivery_token=token,
        )
    )
    assert claim["status"] == "ok" and claim["delivery_state"] == "delivering"
    rec = _run(
        record_execution_receipt(
            tenant_id=TENANT,
            execution_request_id=rid,
            adapter_id="task-adapter",
            delivery_token=token,
            receipt_id="receipt-" + uuid4().hex,
            receipt_status="accepted",
            receipt_payload={"provider_task_id": "t-1"},
        )
    )
    assert rec["status"] == "ok" and rec["execution_state"] == "accepted"

    async def verify():
        c = await _connect()
        try:
            return (
                await c.fetchval(
                    "SELECT status FROM decision_execution_requests WHERE execution_request_id=$1",
                    rid,
                ),
                await c.fetchval(
                    "SELECT count(*) FROM decision_execution_delivery_attempts WHERE execution_request_id=$1",
                    rid,
                ),
                await c.fetchval(
                    "SELECT count(*) FROM decision_outbox_events WHERE event_type='EXECUTION_RECEIPT_RECORDED' AND aggregate_id=$1",
                    rid,
                ),
            )
        finally:
            await c.close()

    assert _run(verify()) == ("accepted", 1, 1)


def test_claim_replay_and_competing_adapter_conflict():
    from persistence import claim_execution_request

    rid = _run(_seed())
    token = "tok-" + uuid4().hex
    first = _run(
        claim_execution_request(
            tenant_id=TENANT,
            execution_request_id=rid,
            adapter_id="a1",
            adapter_kind="task",
            delivery_token=token,
        )
    )
    replay = _run(
        claim_execution_request(
            tenant_id=TENANT,
            execution_request_id=rid,
            adapter_id="a1",
            adapter_kind="task",
            delivery_token=token,
        )
    )
    assert (
        replay["replay"] is True and replay["delivery_attempt_id"] == first["delivery_attempt_id"]
    )
    assert (
        _run(
            claim_execution_request(
                tenant_id=TENANT,
                execution_request_id=rid,
                adapter_id="a2",
                adapter_kind="task",
                delivery_token="other",
            )
        )["reason"]
        == "execution_request_already_claimed"
    )


def test_wrong_tenant_and_kind_fail_closed():
    from persistence import claim_execution_request

    rid = _run(_seed(target="equipment", tenant=OTHER))
    assert (
        _run(
            claim_execution_request(
                tenant_id=TENANT,
                execution_request_id=rid,
                adapter_id="a",
                adapter_kind="equipment",
                delivery_token="t",
            )
        )["status"]
        == "not_found"
    )
    rid2 = _run(_seed(target="equipment"))
    assert (
        _run(
            claim_execution_request(
                tenant_id=TENANT,
                execution_request_id=rid2,
                adapter_id="a",
                adapter_kind="task",
                delivery_token="t",
            )
        )["reason"]
        == "adapter_kind_mismatch"
    )


def test_two_concurrent_claims_yield_one_winner():
    from persistence import claim_execution_request

    rid = _run(_seed())

    async def race():
        return await asyncio.gather(
            claim_execution_request(
                tenant_id=TENANT,
                execution_request_id=rid,
                adapter_id="a1",
                adapter_kind="task",
                delivery_token="t1",
            ),
            claim_execution_request(
                tenant_id=TENANT,
                execution_request_id=rid,
                adapter_id="a2",
                adapter_kind="task",
                delivery_token="t2",
            ),
        )

    results = _run(race())
    assert (
        sum(r["status"] == "ok" for r in results) == 1
        and sum(r["status"] == "conflict" for r in results) == 1
    )


def test_receipt_replay_and_mismatch_conflict():
    from persistence import claim_execution_request, record_execution_receipt

    rid = _run(_seed())
    token = "tok-" + uuid4().hex
    receipt = "rec-" + uuid4().hex
    _run(
        claim_execution_request(
            tenant_id=TENANT,
            execution_request_id=rid,
            adapter_id="a",
            adapter_kind="task",
            delivery_token=token,
        )
    )
    args = dict(
        tenant_id=TENANT,
        execution_request_id=rid,
        adapter_id="a",
        delivery_token=token,
        receipt_id=receipt,
        receipt_status="failed",
        receipt_payload={"reason": "provider rejected"},
    )
    first = _run(record_execution_receipt(**args))
    replay = _run(record_execution_receipt(**args))
    assert first["status"] == "ok" and replay["replay"] is True
    changed = dict(args)
    changed["receipt_payload"] = {"reason": "changed"}
    assert _run(record_execution_receipt(**changed))["reason"] == "receipt_already_recorded"


def test_delivery_identity_and_terminal_receipt_are_immutable():
    import asyncpg
    from persistence import claim_execution_request, record_execution_receipt

    rid = _run(_seed())
    token = "tok-" + uuid4().hex
    claim = _run(
        claim_execution_request(
            tenant_id=TENANT,
            execution_request_id=rid,
            adapter_id="a",
            adapter_kind="task",
            delivery_token=token,
        )
    )
    _run(
        record_execution_receipt(
            tenant_id=TENANT,
            execution_request_id=rid,
            adapter_id="a",
            delivery_token=token,
            receipt_id="r-" + uuid4().hex,
            receipt_status="accepted",
            receipt_payload={},
        )
    )

    async def mutate(sql):
        c = await _connect()
        try:
            await c.execute(sql, claim["delivery_attempt_id"])
        finally:
            await c.close()

    for sql in (
        "UPDATE decision_execution_delivery_attempts SET adapter_id='x' WHERE delivery_attempt_id=$1",
        "UPDATE decision_execution_delivery_attempts SET receipt_status='failed' WHERE delivery_attempt_id=$1",
        "DELETE FROM decision_execution_delivery_attempts WHERE delivery_attempt_id=$1",
    ):
        with pytest.raises(asyncpg.PostgresError):
            _run(mutate(sql))
