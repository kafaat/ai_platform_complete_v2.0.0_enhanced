-- WX-12.1 runtime receipts: rollout-application and retraining-dispatch acknowledgements.
-- These close the runtime<->decision-service loop: the model-registry-adapter reports back the
-- terminal result of applying a rollout plan and of dispatching a retraining request. Both are
-- append-only evidence (no update/delete) and reference their governing WX-11 plan/request.
CREATE TABLE IF NOT EXISTS decision_model_rollout_receipts (
 rollout_receipt_id text PRIMARY KEY, tenant_id uuid NOT NULL, rollout_plan_id text NOT NULL,
 receipt_state text NOT NULL, controller_id text NOT NULL,
 observed_traffic_percent numeric, candidate_artifact_digest text, routing_version text,
 failure_reason text, receipt_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 recorded_by text NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, request_hash text NOT NULL,
 UNIQUE(tenant_id, rollout_plan_id), UNIQUE(tenant_id, idempotency_key),
 FOREIGN KEY (rollout_plan_id) REFERENCES decision_model_rollout_plans(rollout_plan_id),
 CHECK (receipt_state IN ('applied','rollout_failed')),
 CHECK (receipt_state <> 'rollout_failed' OR length(trim(failure_reason)) > 0)
);
CREATE TABLE IF NOT EXISTS decision_model_retraining_dispatch_receipts (
 dispatch_receipt_id text PRIMARY KEY, tenant_id uuid NOT NULL, retraining_request_id text NOT NULL,
 dispatch_state text NOT NULL, dispatcher_id text NOT NULL, job_id text, backend text,
 failure_reason text, receipt_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 recorded_by text NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, request_hash text NOT NULL,
 UNIQUE(tenant_id, retraining_request_id), UNIQUE(tenant_id, idempotency_key),
 FOREIGN KEY (retraining_request_id) REFERENCES decision_model_retraining_requests(retraining_request_id),
 CHECK (dispatch_state IN ('dispatched','dispatch_failed')),
 CHECK (dispatch_state <> 'dispatched' OR length(trim(job_id)) > 0),
 CHECK (dispatch_state <> 'dispatch_failed' OR length(trim(failure_reason)) > 0)
);
-- append-only: reuse the WX-11 completion trigger function (created in migration 014).
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['decision_model_rollout_receipts','decision_model_retraining_dispatch_receipts'] LOOP EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_append_only ON %I',t,t); EXECUTE format('CREATE TRIGGER trg_%s_append_only BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION decision_wx11_completion_append_only()',t,t); END LOOP; END $$;
