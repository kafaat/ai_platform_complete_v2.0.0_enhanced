"""Valid stored parents for delivery/outcome integration fixtures, no commands sent."""

import json
from uuid import uuid4


async def seed_authorized_parents(c, tenant_id):
    did = "dec_" + uuid4().hex
    rid = "rev_" + uuid4().hex
    lin = "lin_" + uuid4().hex
    pid = "xplan_" + uuid4().hex
    aid = "dauth_" + uuid4().hex
    await c.execute(
        "INSERT INTO decision_record(decision_id,tenant_id,decision_type,stage,decision_value,review_state,candidate_lineage_id) VALUES($1,$2::uuid,'candidate','candidate',$3::jsonb,'approved',$4)",
        did,
        tenant_id,
        json.dumps({"candidate_lineage_id": lin}),
        lin,
    )
    await c.execute(
        "INSERT INTO decision_reviews(review_id,decision_id,tenant_id,action,previous_state,new_state,reason,reviewed_by,candidate_lineage_id,idempotency_key,request_hash,policy_version) VALUES($1,$2,$3::uuid,'approve','pending_approval','approved','ok','r',$4,$5,$6,'p1')",
        rid,
        did,
        tenant_id,
        lin,
        "r-" + uuid4().hex,
        uuid4().hex,
    )
    await c.execute(
        "INSERT INTO decision_execution_plans(execution_plan_id,tenant_id,decision_id,review_id,candidate_lineage_id,operation_type,status,idempotency_key,request_hash,created_by) VALUES($1,$2::uuid,$3,$4,$5,'irrigation','planned',$6,$7,'p')",
        pid,
        tenant_id,
        did,
        rid,
        lin,
        "p-" + uuid4().hex,
        uuid4().hex,
    )
    await c.execute(
        "INSERT INTO decision_dispatch_authorizations(dispatch_authorization_id,tenant_id,execution_plan_id,decision_id,review_id,candidate_lineage_id,expected_plan_state,status,policy_version,weather_snapshot_id,resource_snapshot_id,authorization_reason,idempotency_key,request_hash,authorized_by) VALUES($1,$2::uuid,$3,$4,$5,$6,'planned','authorized','p1','w1','r1','ok',$7,$8,'m')",
        aid,
        tenant_id,
        pid,
        did,
        rid,
        lin,
        "a-" + uuid4().hex,
        uuid4().hex,
    )
    return aid, pid, did
