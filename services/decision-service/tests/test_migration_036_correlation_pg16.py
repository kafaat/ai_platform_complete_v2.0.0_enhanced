"""Native PG16 full-runner/real-writer correlation proof in the disposable CI DB.

No deployment or physical command is executed. The inherited fixture permits
only the exact dedicated loopback DSN and uses a fresh nonprivileged LOGIN role.
"""

from types import SimpleNamespace
from uuid import UUID

import asyncpg
import migration_runner as runner
import persistence
import pytest
from test_migration_033_pg16 import OTHER, TENANT
from test_migration_033_pg16 import database as database


@pytest.mark.asyncio
async def test_correlation_follows_real_writers_and_replay(database):
    assert not await database.admin.fetchval(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name='decision_record' AND column_name='correlation_id')"
    )
    assert (await runner.apply_migrations())["ok"]
    payload = SimpleNamespace(
        stage="candidate",
        decision_value={"candidate_lineage_id": "ci-correlation", "season_id": "ci-season"},
        field_id="ci-field",
        decision_type="irrigation",
        region=None,
        confidence=None,
        created_by="ci-only",
    )
    root = await persistence.persist_decision_record(
        tenant_id=TENANT, payload=payload, decision_id="ci-correlation"
    )
    correlation = await database.admin.fetchval(
        "SELECT correlation_id FROM decision_record WHERE decision_id='ci-correlation'"
    )
    assert isinstance(correlation, UUID)
    assert root["correlation_id"] == str(correlation)
    root_replay = await persistence.persist_decision_record(
        tenant_id=TENANT, payload=payload, decision_id="ci-correlation"
    )
    assert root_replay["replayed"] and root_replay["correlation_id"] == str(correlation)
    for tenant, count in [(TENANT, 1), (OTHER, 0)]:
        records = await persistence.list_decision_records(
            tenant_id=tenant, field_id=None, decision_type=None, limit=100
        )
        queue = await persistence.list_review_queue(tenant_id=tenant)
        field_queue = await persistence.list_review_queue(
            tenant_id=tenant, field_id="ci-field", season_id="ci-season"
        )
        assert records["count"] == len(queue) == len(field_queue) == count
        if count:
            assert records["decisions"][0]["correlation_id"] == str(correlation)
            assert queue[0]["correlation_id"] == str(correlation)
            assert field_queue[0]["correlation_id"] == str(correlation)
    review_args = dict(
        tenant_id=TENANT,
        decision_id="ci-correlation",
        action="approve",
        new_state="approved",
        reason="disposable CI",
        reviewed_by="ci-only",
        candidate_lineage_id="ci-correlation",
        idempotency_key="ci-review-correlation",
        policy_version="ci-policy",
        decision_value_digest=root["decision_value_digest"],
    )
    review = await persistence.review_decision(**review_args)
    plan_args = dict(
        tenant_id=TENANT,
        decision_id="ci-correlation",
        review_id=review["review_id"],
        candidate_lineage_id="ci-correlation",
        idempotency_key="ci-plan-correlation",
        created_by="ci-only",
        payload=SimpleNamespace(
            operation_type="inspection",
            planned_start=None,
            planned_end=None,
            target_zone_ids=[],
            required_resources=[],
            constraints={},
            safety_conditions={},
            weather_window_reference=None,
        ),
    )
    plan = await persistence.create_execution_plan(**plan_args)
    auth = await persistence.authorize_dispatch(
        tenant_id=TENANT,
        decision_id="ci-correlation",
        review_id=review["review_id"],
        execution_plan_id=plan["execution_plan_id"],
        candidate_lineage_id="ci-correlation",
        idempotency_key="ci-auth-correlation",
        authorized_by="ci-only",
        payload=SimpleNamespace(
            expected_plan_state="planned",
            policy_version="ci-policy",
            weather_snapshot_id="ci-weather",
            resource_snapshot_id="ci-resources",
            authorization_reason="isolated SQL proof only",
        ),
    )
    request_args = dict(
        tenant_id=TENANT,
        dispatch_authorization_id=auth["dispatch_authorization_id"],
        requested_by="ci-only",
        payload=SimpleNamespace(
            execution_plan_id=plan["execution_plan_id"],
            decision_id="ci-correlation",
            target_type="task",
            target_id="ci-never-delivered",
            operation_type="inspection",
            command_payload={},
            idempotency_key="ci-request-correlation",
        ),
    )
    request = await persistence.create_execution_request(**request_args)
    for result in [review, plan, auth, request]:
        assert result["status"] == "ok"
        assert result["correlation_id"] == str(correlation)
    for method, args in [
        (persistence.review_decision, review_args),
        (persistence.create_execution_plan, plan_args),
        (persistence.create_execution_request, request_args),
    ]:
        replay = await method(**args)
        assert replay["replay"] is True
        assert replay["correlation_id"] == str(correlation)
    assert await persistence.review_decision(**{**review_args, "tenant_id": OTHER}) == {
        "status": "not_found"
    }
    assert (await runner.apply_migrations())["applied_now"] == []
    assert (
        await database.admin.fetchval(
            "SELECT decision_value_digest FROM decision_record WHERE decision_id='ci-correlation'"
        )
        == root["decision_value_digest"]
    )
    app = await database.app_connection()
    try:
        async with app.transaction():
            await app.execute("SELECT set_config('app.current_tenant',$1,true)", TENANT)
            with pytest.raises(asyncpg.CheckViolationError, match="correlation"):
                async with app.transaction():
                    await app.execute(
                        "UPDATE decision_execution_requests SET correlation_id=gen_random_uuid() "
                        "WHERE execution_request_id=$1",
                        request["execution_request_id"],
                    )
            await app.execute("SELECT set_config('app.current_tenant',$1,true)", OTHER)
            assert await app.fetchval("SELECT count(*) FROM decision_record") == 0
            # Child invoker lookup fails before its INSERT RLS check. The error
            # means unavailable parent, never a cross-tenant existence oracle.
            for current_tenant, new_tenant in [(OTHER, OTHER), ("", TENANT)]:
                await app.execute("SELECT set_config('app.current_tenant',$1,true)", current_tenant)
                with pytest.raises(asyncpg.ForeignKeyViolationError, match="parent unavailable"):
                    async with app.transaction():
                        await app.execute(
                            "INSERT INTO decision_reviews "
                            "(review_id,decision_id,tenant_id,action,previous_state,new_state,"
                            "reviewed_by,candidate_lineage_id,idempotency_key,request_hash,policy_version) "
                            "VALUES('cross-review','ci-correlation',$1::uuid,'approve',"
                            "'pending_approval','approved','ci-only','ci-correlation',"
                            "'cross-review','ci-hash','ci-policy')",
                            new_tenant,
                        )
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    async with app.transaction():
                        await app.execute(
                            "INSERT INTO decision_record(decision_id,tenant_id) "
                            "VALUES('forbidden-root',$1::uuid)",
                            TENANT,
                        )
    finally:
        await app.close()
