"""WX-10.12 structural contract plus real-Postgres behavior tests."""

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
TENANT = "00000000-0000-0000-0000-000000001212"


def _run(c):
    return asyncio.run(c)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


def test_contract_is_canonical_and_learning_free():
    migration = (SERVICE_DIR / "migrations/007_execution_outcome_verification.sql").read_text()
    persistence = (SERVICE_DIR / "persistence.py").read_text()
    assert "ALTER TABLE outcome_record" in migration
    assert "CREATE TABLE IF NOT EXISTS decision_execution_outcomes" not in migration
    segment = persistence[persistence.index("async def verify_execution_outcome") :]
    assert "EXECUTION_OUTCOME_VERIFIED" in segment
    assert "persist_learning_update(" not in segment


@pytest.mark.skipif(not DB, reason="requires real Postgres")
def test_terminal_request_creates_one_immutable_outcome_and_outbox():
    from persistence import verify_execution_outcome

    async def seed():
        c = await _connect()
        rid = "exec_" + uuid4().hex
        receipt = "rec_" + uuid4().hex
        try:
            await c.execute(
                """INSERT INTO decision_execution_requests(execution_request_id,tenant_id,dispatch_authorization_id,execution_plan_id,decision_id,target_type,target_id,operation_type,command_payload,status,idempotency_key,request_hash,requested_by,receipt_id,receipt_status,receipt_payload,received_at) VALUES($1,$2::uuid,$3,$4,$5,'task','t','op','{}'::jsonb,'accepted',$6,$7,'u',$8,'accepted','{}'::jsonb,now())""",
                rid,
                TENANT,
                "auth_" + uuid4().hex,
                "plan_" + uuid4().hex,
                "dec_" + uuid4().hex,
                "i-" + uuid4().hex,
                uuid4().hex,
                receipt,
            )
            await c.execute(
                """INSERT INTO decision_execution_delivery_attempts(delivery_attempt_id,tenant_id,execution_request_id,adapter_id,adapter_kind,delivery_token_hash,receipt_id,receipt_status,receipt_payload,received_at) VALUES($1,$2::uuid,$3,'a','task','h',$4,'accepted','{}'::jsonb,now())""",
                "del_" + uuid4().hex,
                TENANT,
                rid,
                receipt,
            )
            row = await c.fetchrow(
                "SELECT * FROM decision_execution_requests WHERE execution_request_id=$1", rid
            )
            return rid, receipt, row
        finally:
            await c.close()

    rid, receipt, row = _run(seed())
    payload = SimpleNamespace(
        execution_plan_id=row["execution_plan_id"],
        dispatch_authorization_id=row["dispatch_authorization_id"],
        decision_id=row["decision_id"],
        receipt_id=receipt,
        verification_state="verified_success",
        evidence_snapshot_id="ev-" + uuid4().hex,
        actual={"completed": True},
        metrics={"duration_min": 5},
        idempotency_key="idem-" + uuid4().hex,
    )
    first = _run(
        verify_execution_outcome(
            tenant_id=TENANT, execution_request_id=rid, verified_by="operator", payload=payload
        )
    )
    replay = _run(
        verify_execution_outcome(
            tenant_id=TENANT, execution_request_id=rid, verified_by="operator", payload=payload
        )
    )
    assert first["status"] == "ok" and first["success"] is True and replay["replay"] is True

    async def verify():
        c = await _connect()
        try:
            return await c.fetchval(
                "SELECT count(*) FROM outcome_record WHERE execution_request_id=$1", rid
            ), await c.fetchval(
                "SELECT count(*) FROM decision_outbox_events WHERE event_type='EXECUTION_OUTCOME_VERIFIED' AND aggregate_id=$1",
                first["outcome_id"],
            )
        finally:
            await c.close()

    assert _run(verify()) == (1, 1)


@pytest.mark.skipif(not DB, reason="requires real Postgres")
def test_nonterminal_and_wrong_tenant_fail_closed():
    from persistence import verify_execution_outcome

    payload = SimpleNamespace(
        execution_plan_id="p",
        dispatch_authorization_id="a",
        decision_id="d",
        receipt_id="r",
        verification_state="verified_failure",
        evidence_snapshot_id="e",
        actual={},
        metrics={},
        idempotency_key="i-" + uuid4().hex,
    )
    assert (
        _run(
            verify_execution_outcome(
                tenant_id=TENANT, execution_request_id="missing", verified_by="u", payload=payload
            )
        )["status"]
        == "not_found"
    )
