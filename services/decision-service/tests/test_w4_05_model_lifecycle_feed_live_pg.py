"""W4-05: with the WX-12 loop stopped, the runtime-work feed leaves its rows pending and untouched.

Against real Postgres (SoR tables, migrations 001-039). The feed query itself drops the five WX-12
work types while ``include_model_lifecycle`` is false: their rows are neither returned nor leased,
so they reappear unchanged when the loop is turned on. The WX-11.6 activation and rollback
commands come out byte-identical either way. MODEL_LIFECYCLE_CERTIFICATION_REQUIRED=1 (set by
the CI step) turns a missing database into a failure instead of a skip.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
DB = os.getenv("DATABASE_URL", "").strip()
REQUIRED = os.getenv("MODEL_LIFECYCLE_CERTIFICATION_REQUIRED", "").strip() == "1"
pytestmark = pytest.mark.skipif(not DB and not REQUIRED, reason="requires real Postgres")

WX11 = ("activation_command", "rollback_command")


def _run(c):
    return asyncio.run(c)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


async def _seed(tenant: str) -> dict[str, str]:
    """A pending rollout plan (WX-12), a pending activation command and a pending rollback
    command (WX-11.6), all in one fresh tenant."""
    from _model_chain import seed_activated_model

    c = await _connect()
    try:
        activated = await seed_activated_model(c, tenant=tenant, model_id="m_" + uuid4().hex[:8])
        plan_id = "rollout_" + uuid4().hex
        await c.execute(
            """INSERT INTO decision_model_rollout_plans(rollout_plan_id,tenant_id,activation_receipt_id,mode,traffic_percent,policy,requested_by,idempotency_key,request_hash)
               VALUES($1,$2::uuid,$3,'canary',10,'{}'::jsonb,'planner',$4,'h')""",
            plan_id,
            tenant,
            activated["activation_receipt_id"],
            "idem_" + uuid4().hex,
        )
        rollback_id = "rbcmd_" + uuid4().hex[:20]
        await c.execute(
            """INSERT INTO decision_model_registry_rollback_commands
               (rollback_command_id,tenant_id,activation_receipt_id,activation_command_id,
                registry_alias,target_environment,restore_artifact_uri,restore_artifact_digest,
                replace_artifact_uri,replace_artifact_digest,requested_by,reason,
                idempotency_key,request_hash)
               VALUES($1,$2::uuid,$3,$4,'alias','staging','s3://prev',$5,'s3://m',$6,
                      'tester','rollback test',$7,'h')""",
            rollback_id,
            tenant,
            activated["activation_receipt_id"],
            activated["activation_command_id"],
            "e" * 64,
            "d" * 64,
            "idem_" + uuid4().hex,
        )
        pending = await seed_activated_model(
            c, tenant=tenant, model_id="m_" + uuid4().hex[:8], with_receipt=False
        )
        return {
            "rollout_plan_id": plan_id,
            "rollback_command_id": rollback_id,
            "activation_command_id": pending["activation_command_id"],
        }
    finally:
        await c.close()


async def _claims(tenant: str, work_type: str, work_key: str) -> int:
    c = await _connect()
    try:
        return await c.fetchval(
            """SELECT count(*) FROM decision_model_runtime_work_claims
               WHERE tenant_id=$1::uuid AND work_type=$2 AND work_key=$3""",
            tenant,
            work_type,
            work_key,
        )
    finally:
        await c.close()


async def _plan_row(plan_id: str) -> dict:
    c = await _connect()
    try:
        row = await c.fetchrow(
            "SELECT * FROM decision_model_rollout_plans WHERE rollout_plan_id=$1", plan_id
        )
        return dict(row)
    finally:
        await c.close()


def _feed(tenant: str, include: bool | None) -> list[dict]:
    from persistence import list_runtime_work

    result = _run(
        list_runtime_work(
            tenant_id=tenant, worker_id="w4-05-worker", limit=100, include_model_lifecycle=include
        )
    )
    assert result["status"] == "ok"
    return result["items"]


def _wx11(items: list[dict]) -> list[str]:
    return [json.dumps(i, sort_keys=True) for i in items if i["work_type"] in WX11]


def test_a_pending_rollout_survives_off_never_appears_and_returns_on(monkeypatch):
    from persistence import MODEL_LIFECYCLE_WORK_TYPES

    tenant = str(uuid4())
    ids = _run(_seed(tenant))
    before = _run(_plan_row(ids["rollout_plan_id"]))

    monkeypatch.delenv("DECISION_MODEL_LIFECYCLE_ENABLED", raising=False)
    for include in (False, None):  # explicit off, and the default with the flag unset
        off = _feed(tenant, include)
        assert not [i for i in off if i["work_type"] in MODEL_LIFECYCLE_WORK_TYPES], off
    assert _run(_claims(tenant, "rollout_apply", ids["rollout_plan_id"])) == 0
    assert _run(_plan_row(ids["rollout_plan_id"])) == before

    on = _feed(tenant, True)
    rollouts = [i for i in on if i["work_type"] == "rollout_apply"]
    assert [i["payload"]["rollout_plan_id"] for i in rollouts] == [ids["rollout_plan_id"]]
    assert _run(_claims(tenant, "rollout_apply", ids["rollout_plan_id"])) == 1


def test_activation_and_rollback_commands_are_byte_identical_either_way():
    tenant = str(uuid4())
    ids = _run(_seed(tenant))
    off = _wx11(_feed(tenant, False))
    on = _wx11(_feed(tenant, True))
    assert off == on
    types = {json.loads(i)["work_type"] for i in off}
    assert types == set(WX11), types
    payloads = [json.loads(i)["payload"] for i in off]
    assert {p.get("activation_command_id") for p in payloads} >= {ids["activation_command_id"]}
    assert {p.get("rollback_command_id") for p in payloads} >= {ids["rollback_command_id"]}


def test_off_leaves_no_lease_for_any_wx12_item():
    tenant = str(uuid4())
    _run(_seed(tenant))

    async def _count() -> int:
        c = await _connect()
        try:
            return await c.fetchval(
                "SELECT count(*) FROM decision_model_runtime_work_claims WHERE tenant_id=$1::uuid",
                tenant,
            )
        finally:
            await c.close()

    _feed(tenant, False)
    assert _run(_count()) == 0
    _feed(tenant, True)
    assert _run(_count()) > 0
