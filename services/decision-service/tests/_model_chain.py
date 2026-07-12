"""Shared test helper: seed a FULL activated-model chain that satisfies the cohort
lineage triggers (migrations 021-023).

Since the runtime cohort-lineage increment, orphan direct-seeds are rejected by design:
every rollout plan needs an 'activated' receipt, every receipt a command, every command a
review, and so on back to the evaluation run. This helper inserts the minimal honest chain
(all agronomic_cohorts at their '{}' default, fingerprints NULL) so runtime-layer tests
can exercise their own contracts without duplicating the whole governance flow.
"""

from __future__ import annotations

from uuid import uuid4


async def seed_activated_model(
    conn,
    *,
    tenant: str,
    model_id: str,
    feature_set_id: str = "f1",
    target_environment: str = "staging",
) -> dict[str, str]:
    """Insert evaluation→promotion→request→review→command→claim→activated receipt."""
    digest = uuid4().hex + uuid4().hex  # unique per chain (uq_model_eval_artifact_digest)
    ids = {
        "evaluation_run_id": "eval_" + uuid4().hex[:20],
        "promotion_decision_id": "promo_" + uuid4().hex[:20],
        "activation_request_id": "actreq_" + uuid4().hex[:20],
        "activation_review_id": "actrev_" + uuid4().hex[:20],
        "activation_command_id": "actcmd_" + uuid4().hex[:20],
        "activation_claim_id": "actclm_" + uuid4().hex[:20],
        "activation_receipt_id": "actrcp_" + uuid4().hex[:20],
    }
    await conn.execute(
        """INSERT INTO decision_model_evaluation_runs
           (evaluation_run_id,tenant_id,model_id,feature_set_id,dataset_fingerprint,dataset_count,
            evaluator_version,baseline_metrics,candidate_metrics,candidate_artifact_uri,
            candidate_artifact_digest,artifact_format,evaluation_state,idempotency_key,request_hash,evaluated_by)
           VALUES($1,$2::uuid,$3,$4,$5,1,'ev1','{}'::jsonb,'{}'::jsonb,'s3://m',$6,'onnx','evaluated',$7,'h','tester')""",
        ids["evaluation_run_id"],
        tenant,
        model_id,
        feature_set_id,
        "a" * 64,
        digest,
        "idem_" + uuid4().hex,
    )
    await conn.execute(
        """INSERT INTO decision_model_promotion_decisions
           (promotion_decision_id,tenant_id,evaluation_run_id,model_id,feature_set_id,policy_version,
            policy_snapshot,metric_deltas,decision_state,decision_reason,candidate_artifact_uri,
            candidate_artifact_digest,idempotency_key,request_hash,decided_by)
           VALUES($1,$2::uuid,$3,$4,$5,'p1','{}'::jsonb,'{}'::jsonb,'promotion_eligible','ok','s3://m',$6,$7,'h','tester')""",
        ids["promotion_decision_id"],
        tenant,
        ids["evaluation_run_id"],
        model_id,
        feature_set_id,
        digest,
        "idem_" + uuid4().hex,
    )
    await conn.execute(
        """INSERT INTO decision_model_activation_requests
           (activation_request_id,tenant_id,promotion_decision_id,evaluation_run_id,model_id,feature_set_id,
            candidate_artifact_uri,candidate_artifact_digest,target_environment,requested_state,
            requested_by,idempotency_key,request_hash)
           VALUES($1,$2::uuid,$3,$4,$5,$6,'s3://m',$7,$8,'pending_activation_approval','tester',$9,'h')""",
        ids["activation_request_id"],
        tenant,
        ids["promotion_decision_id"],
        ids["evaluation_run_id"],
        model_id,
        feature_set_id,
        digest,
        target_environment,
        "idem_" + uuid4().hex,
    )
    await conn.execute(
        """INSERT INTO decision_model_activation_reviews
           (activation_review_id,tenant_id,activation_request_id,review_decision,review_reason,
            registry_alias,previous_artifact_uri,previous_artifact_digest,reviewed_by,idempotency_key,request_hash)
           VALUES($1,$2::uuid,$3,'approved','ok','alias','s3://prev',$4,'tester',$5,'h')""",
        ids["activation_review_id"],
        tenant,
        ids["activation_request_id"],
        "e" * 64,
        "idem_" + uuid4().hex,
    )
    await conn.execute(
        """INSERT INTO decision_model_registry_activation_commands
           (activation_command_id,tenant_id,activation_review_id,activation_request_id,model_id,feature_set_id,
            target_environment,registry_alias,candidate_artifact_uri,candidate_artifact_digest,
            previous_artifact_uri,previous_artifact_digest,created_by)
           VALUES($1,$2::uuid,$3,$4,$5,$6,$7,'alias','s3://m',$8,'s3://prev',$9,'tester')""",
        ids["activation_command_id"],
        tenant,
        ids["activation_review_id"],
        ids["activation_request_id"],
        model_id,
        feature_set_id,
        target_environment,
        digest,
        "e" * 64,
    )
    await conn.execute(
        """INSERT INTO decision_model_registry_activation_claims
           (activation_claim_id,tenant_id,activation_command_id,adapter_id,delivery_token_hash)
           VALUES($1,$2::uuid,$3,'adapter-test',$4)""",
        ids["activation_claim_id"],
        tenant,
        ids["activation_command_id"],
        "f" * 64,
    )
    await conn.execute(
        """INSERT INTO decision_model_registry_activation_receipts
           (activation_receipt_id,tenant_id,activation_command_id,activation_claim_id,receipt_state,
            active_artifact_uri,active_artifact_digest,registry_version,receipt_payload,recorded_by,
            idempotency_key,request_hash)
           VALUES($1,$2::uuid,$3,$4,'activated','s3://m',$5,'1','{}'::jsonb,'adapter-test',$6,'h')""",
        ids["activation_receipt_id"],
        tenant,
        ids["activation_command_id"],
        ids["activation_claim_id"],
        digest,
        "idem_" + uuid4().hex,
    )
    return ids
