-- WX-11.7..WX-11.12 completion: rollback evidence, active-state, verification, rollout, monitoring, retraining.
CREATE TABLE IF NOT EXISTS decision_model_registry_rollback_claims (
 rollback_claim_id text PRIMARY KEY, tenant_id uuid NOT NULL, rollback_command_id text NOT NULL,
 adapter_id text NOT NULL, delivery_token_hash text NOT NULL, claimed_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id, rollback_command_id),
 FOREIGN KEY (rollback_command_id) REFERENCES decision_model_registry_rollback_commands(rollback_command_id),
 CHECK (delivery_token_hash ~ '^[a-f0-9]{64}$')
);
CREATE TABLE IF NOT EXISTS decision_model_registry_rollback_receipts (
 rollback_receipt_id text PRIMARY KEY, tenant_id uuid NOT NULL, rollback_command_id text NOT NULL,
 rollback_claim_id text NOT NULL, receipt_state text NOT NULL,
 active_artifact_uri text, active_artifact_digest text, registry_version text, failure_reason text,
 receipt_payload jsonb NOT NULL DEFAULT '{}'::jsonb, recorded_by text NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, request_hash text NOT NULL,
 UNIQUE(tenant_id, rollback_command_id), UNIQUE(tenant_id, idempotency_key),
 FOREIGN KEY (rollback_command_id) REFERENCES decision_model_registry_rollback_commands(rollback_command_id),
 FOREIGN KEY (rollback_claim_id) REFERENCES decision_model_registry_rollback_claims(rollback_claim_id),
 CHECK (receipt_state IN ('rolled_back','rollback_failed')),
 CHECK (receipt_state <> 'rolled_back' OR (length(trim(active_artifact_uri))>0 AND active_artifact_digest ~ '^[a-fA-F0-9]{64}$')),
 CHECK (receipt_state <> 'rollback_failed' OR length(trim(failure_reason))>0)
);
CREATE TABLE IF NOT EXISTS decision_model_post_activation_verifications (
 verification_id text PRIMARY KEY, tenant_id uuid NOT NULL, activation_receipt_id text NOT NULL,
 verification_state text NOT NULL, artifact_digest text NOT NULL, checks jsonb NOT NULL,
 latency_ms numeric, error_rate numeric, verified_by text NOT NULL, verified_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, request_hash text NOT NULL,
 UNIQUE(tenant_id, activation_receipt_id), UNIQUE(tenant_id, idempotency_key),
 CHECK (verification_state IN ('verified_healthy','verified_degraded','verification_failed')),
 CHECK (artifact_digest ~ '^[a-fA-F0-9]{64}$')
);
CREATE TABLE IF NOT EXISTS decision_model_rollout_plans (
 rollout_plan_id text PRIMARY KEY, tenant_id uuid NOT NULL, activation_receipt_id text NOT NULL,
 mode text NOT NULL, traffic_percent numeric NOT NULL, rollout_state text NOT NULL DEFAULT 'planned',
 policy jsonb NOT NULL, requested_by text NOT NULL, requested_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, request_hash text NOT NULL,
 UNIQUE(tenant_id, activation_receipt_id), UNIQUE(tenant_id, idempotency_key),
 CHECK (mode IN ('shadow','canary','full')), CHECK (traffic_percent >= 0 AND traffic_percent <= 100),
 CHECK (rollout_state='planned')
);
CREATE TABLE IF NOT EXISTS decision_model_monitoring_snapshots (
 monitoring_snapshot_id text PRIMARY KEY, tenant_id uuid NOT NULL, model_id text NOT NULL,
 feature_set_id text, target_environment text NOT NULL, window_start timestamptz NOT NULL, window_end timestamptz NOT NULL,
 sample_count integer NOT NULL, metrics jsonb NOT NULL, drift_state text NOT NULL,
 captured_by text NOT NULL, captured_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, request_hash text NOT NULL,
 UNIQUE(tenant_id, idempotency_key),
 CHECK (sample_count >= 0), CHECK (drift_state IN ('stable','warning','critical')),
 CHECK (window_end > window_start)
);
CREATE TABLE IF NOT EXISTS decision_model_retraining_requests (
 retraining_request_id text PRIMARY KEY, tenant_id uuid NOT NULL, model_id text NOT NULL,
 feature_set_id text, dataset_fingerprint text NOT NULL, training_manifest jsonb NOT NULL,
 code_version text NOT NULL, hyperparameters jsonb NOT NULL, request_state text NOT NULL DEFAULT 'queued',
 requested_by text NOT NULL, requested_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, request_hash text NOT NULL,
 UNIQUE(tenant_id, idempotency_key), CHECK (request_state='queued'),
 CHECK (dataset_fingerprint ~ '^[a-fA-F0-9]{64}$')
);
CREATE OR REPLACE FUNCTION decision_wx11_completion_append_only() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'WX-11 completion evidence is append-only'; END; $$ LANGUAGE plpgsql;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['decision_model_registry_rollback_claims','decision_model_registry_rollback_receipts','decision_model_post_activation_verifications','decision_model_rollout_plans','decision_model_monitoring_snapshots','decision_model_retraining_requests'] LOOP EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_append_only ON %I',t,t); EXECUTE format('CREATE TRIGGER trg_%s_append_only BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION decision_wx11_completion_append_only()',t,t); END LOOP; END $$;
