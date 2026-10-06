"""WX-10.9 execution-plan boundary against real Postgres."""

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
TENANT = "00000000-0000-0000-0000-000000001099"
OTHER = "00000000-0000-0000-0000-000000002099"


def _run(coro):
    return asyncio.run(coro)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


async def _seed(*, state="approved", tenant=TENANT):
    decision_id = "dec_" + uuid4().hex
    review_id = "rev_" + uuid4().hex
    lineage = "lin_" + uuid4().hex
    conn = await _connect()
    try:
        await conn.execute(
            """INSERT INTO decision_record
               (decision_id,tenant_id,decision_type,stage,decision_value,review_state,candidate_lineage_id)
               VALUES ($1,$2::uuid,'crop_decision_candidate','candidate',$3::jsonb,$4,$5)""",
            decision_id,
            tenant,
            json.dumps({"candidate_lineage_id": lineage, "evidence": {"gdd": 42}}),
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
        return decision_id, review_id, lineage
    finally:
        await conn.close()


def _payload():
    return SimpleNamespace(
        operation_type="irrigation",
        planned_start=None,
        planned_end=None,
        target_zone_ids=["z1"],
        required_resources=[{"type": "water"}],
        constraints={"max_mm": 20},
        safety_conditions={"wind_ok": True},
        weather_window_reference={"snapshot_id": "wx1"},
    )


def _create(decision_id, review_id, lineage, **over):
    from persistence import create_execution_plan

    args = dict(
        tenant_id=TENANT,
        decision_id=decision_id,
        review_id=review_id,
        candidate_lineage_id=lineage,
        idempotency_key="idem-" + uuid4().hex,
        created_by="planner",
        payload=_payload(),
    )
    args.update(over)
    return create_execution_plan(**args)


def test_approved_decision_creates_one_planned_record_and_outbox():
    did, rid, lin = _run(_seed())
    res = _run(_create(did, rid, lin))
    assert res["status"] == "ok" and res["plan_state"] == "planned"
    assert res["authoritative"] is True and res["persisted"] is True

    async def counts():
        conn = await _connect()
        try:
            return (
                await conn.fetchval(
                    "SELECT count(*) FROM decision_execution_plans WHERE decision_id=$1", did
                ),
                await conn.fetchval(
                    "SELECT count(*) FROM decision_outbox_events WHERE event_type='EXECUTION_PLAN_CREATED' AND payload->>'decision_id'=$1",
                    did,
                ),
            )
        finally:
            await conn.close()

    assert _run(counts()) == (1, 1)


def test_rejected_decision_conflicts():
    did, rid, lin = _run(_seed(state="rejected"))
    res = _run(_create(did, rid, lin))
    assert res == {"status": "conflict", "reason": "decision_not_approved"}


def test_wrong_tenant_is_not_found_without_oracle():
    did, rid, lin = _run(_seed(tenant=OTHER))
    assert _run(_create(did, rid, lin))["status"] == "not_found"


def test_lineage_and_review_mismatch_conflict():
    did, rid, lin = _run(_seed())
    assert _run(_create(did, rid, "wrong"))["reason"] == "candidate_lineage_mismatch"
    assert _run(_create(did, "wrong", lin))["reason"] == "review_id_mismatch"


def test_idempotent_replay_and_payload_mismatch():
    did, rid, lin = _run(_seed())
    key = "idem-" + uuid4().hex
    first = _run(_create(did, rid, lin, idempotency_key=key))
    replay = _run(_create(did, rid, lin, idempotency_key=key))
    assert replay["replay"] is True and replay["execution_plan_id"] == first["execution_plan_id"]
    changed = _payload()
    changed.operation_type = "spraying"
    res = _run(_create(did, rid, lin, idempotency_key=key, payload=changed))
    assert res == {"status": "conflict", "reason": "idempotency_key_payload_mismatch"}


def test_two_concurrent_creates_yield_one_plan():
    did, rid, lin = _run(_seed())

    async def race():
        from persistence import create_execution_plan

        common = dict(
            tenant_id=TENANT,
            decision_id=did,
            review_id=rid,
            candidate_lineage_id=lin,
            created_by="planner",
            payload=_payload(),
        )
        return await asyncio.gather(
            create_execution_plan(idempotency_key="a-" + uuid4().hex, **common),
            create_execution_plan(idempotency_key="b-" + uuid4().hex, **common),
        )

    results = _run(race())
    assert sum(r["status"] == "ok" for r in results) == 1
    assert sum(r["status"] == "conflict" for r in results) == 1


def test_execution_plan_is_append_only():
    import asyncpg

    did, rid, lin = _run(_seed())
    res = _run(_create(did, rid, lin))

    async def mutate(sql):
        conn = await _connect()
        try:
            await conn.execute(sql, res["execution_plan_id"])
        finally:
            await conn.close()

    for sql in (
        "UPDATE decision_execution_plans SET operation_type='x' WHERE execution_plan_id=$1",
        "DELETE FROM decision_execution_plans WHERE execution_plan_id=$1",
    ):
        with pytest.raises(asyncpg.PostgresError):
            _run(mutate(sql))


# ── IRRIGATION-MANUAL-PLAN-NOT-BOUND-TO-DECISION-AMOUNT-01 (035) ────────────────────────
# Owner decision (2026-10-06): a manual irrigation plan binds to the approved decision's
# target_refill_mm within ±10%, on the same field, for the approved version only.
def _irrigation_value(*, target=20.0, should=True, lineage="lin_irr"):
    return {
        "decision_type": "irrigation",
        "field_id": "fld-1",
        "candidate_lineage_id": lineage,
        "recommendation": {"should_irrigate": should, "target_refill_mm": target},
    }


async def _seed_irrigation(*, approved_digest="auto", **value_kw):
    from persistence import decision_value_digest

    decision_id = "dec_" + uuid4().hex
    review_id = "rev_" + uuid4().hex
    lineage = "lin_" + uuid4().hex
    value = _irrigation_value(lineage=lineage, **value_kw)
    digest = decision_value_digest(value)
    conn = await _connect()
    try:
        await conn.execute(
            """INSERT INTO decision_record
               (decision_id,tenant_id,field_id,decision_type,stage,decision_value,review_state,
                candidate_lineage_id,decision_value_digest)
               VALUES ($1,$2::uuid,'fld-1','irrigation','candidate',$3::jsonb,'approved',$4,$5)""",
            decision_id,
            TENANT,
            json.dumps(value),
            lineage,
            digest,
        )
        await conn.execute(
            """INSERT INTO decision_reviews
               (review_id,decision_id,tenant_id,action,previous_state,new_state,reason,reviewed_by,
                candidate_lineage_id,idempotency_key,request_hash,policy_version,
                approved_decision_value_digest)
               VALUES ($1,$2,$3::uuid,'approve','pending_approval','approved','ok','reviewer',
                       $4,$5,$6,'p1',$7)""",
            review_id,
            decision_id,
            TENANT,
            lineage,
            "seed-" + uuid4().hex,
            uuid4().hex,
            digest if approved_digest == "auto" else approved_digest,
        )
        return decision_id, review_id, lineage, digest
    finally:
        await conn.close()


def _manual(**constraints):
    base = {"field_id": "fld-1", "target_depth_mm": 20.0}
    base.update(constraints)
    return SimpleNamespace(
        operation_type="manual_irrigation",
        planned_start=None,
        planned_end=None,
        target_zone_ids=[],
        required_resources=[],
        constraints=base,
        safety_conditions={},
        weather_window_reference=None,
    )


@pytest.mark.parametrize("depth", [18.0, 20.0, 22.0])
def test_manual_plan_within_ten_percent_binds_the_approved_version(depth):
    did, rid, lin, digest = _run(_seed_irrigation())
    res = _run(_create(did, rid, lin, payload=_manual(target_depth_mm=depth)))
    assert res["status"] == "ok", res
    assert res["decision_value_digest"] == digest


@pytest.mark.parametrize(
    ("seed_kw", "constraints", "reason"),
    [
        ({}, {"target_depth_mm": 22.5}, "plan_amount_diverges_from_decision"),
        ({}, {"target_depth_mm": 17.5}, "plan_amount_diverges_from_decision"),
        ({}, {"target_depth_mm": None}, "plan_amount_diverges_from_decision"),
        ({}, {"field_id": "fld-other"}, "plan_field_differs_from_decision"),
        ({"should": False}, {}, "decision_does_not_recommend_irrigation"),
        ({"target": None}, {}, "decision_has_no_refill_target"),
        ({"approved_digest": None}, {}, "decision_version_unbound"),
        ({"approved_digest": "0" * 64}, {}, "decision_version_mismatch"),
    ],
)
def test_manual_plan_is_refused_when_it_does_not_match_the_approved_decision(
    seed_kw, constraints, reason
):
    did, rid, lin, _ = _run(_seed_irrigation(**seed_kw))
    res = _run(_create(did, rid, lin, payload=_manual(**constraints)))
    assert res == {"status": "conflict", "reason": reason}


def test_plan_state_reports_the_bound_version_for_the_live_recheck():
    from persistence import get_execution_plan_state

    did, rid, lin, digest = _run(_seed_irrigation())
    plan = _run(_create(did, rid, lin, payload=_manual()))
    state = _run(
        get_execution_plan_state(tenant_id=TENANT, execution_plan_id=plan["execution_plan_id"])
    )
    assert state["bound"] is True
    assert state["plan_digest"] == plan["plan_digest"]
    assert state["decision_value_digest"] == state["current_decision_value_digest"] == digest
    assert state["review_state"] == "approved"
    other = _run(
        get_execution_plan_state(tenant_id=OTHER, execution_plan_id=plan["execution_plan_id"])
    )
    assert other == {"status": "not_found"}  # tenant-scoped, no oracle
