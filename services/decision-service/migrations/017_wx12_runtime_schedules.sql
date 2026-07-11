-- WX-12.3 durable runtime schedules: make monitoring windows and active-state reconciliation
-- actually flow through the runtime-work feed (they were handled by the supervisor but never
-- emitted — dormant code). A schedule row is durable CONFIG (period + anchor + enabled), not
-- evidence: progression is derived from the append-only evidence itself (monitoring snapshots /
-- reconcile evidence), so no mutable "last run" state can drift or be lost. No schedule rows ⇒
-- zero emission ⇒ zero behavior change (the enablement flag IS the row).
CREATE TABLE IF NOT EXISTS decision_model_runtime_schedules (
 schedule_id text PRIMARY KEY, tenant_id uuid NOT NULL,
 kind text NOT NULL, model_id text NOT NULL, feature_set_id text,
 target_environment text NOT NULL, period_seconds integer NOT NULL,
 anchor_at timestamptz NOT NULL DEFAULT now(), enabled boolean NOT NULL DEFAULT true,
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, request_hash text NOT NULL,
 UNIQUE(tenant_id, kind, model_id, target_environment),
 UNIQUE(tenant_id, idempotency_key),
 CHECK (kind IN ('monitoring_window','active_state_reconcile')),
 CHECK (period_seconds >= 60),
 CHECK (target_environment IN ('staging','production'))
);
-- Append-only reconcile evidence: durable record of projection-vs-registry comparison. This is
-- what makes registry drift / manual alias changes / split-brain auditable instead of log-only.
CREATE TABLE IF NOT EXISTS decision_model_reconcile_evidence (
 reconcile_id text PRIMARY KEY, tenant_id uuid NOT NULL, schedule_id text,
 model_id text NOT NULL, feature_set_id text, target_environment text NOT NULL,
 expected_artifact_digest text NOT NULL, observed_artifact_digest text NOT NULL,
 drift_detected boolean NOT NULL, registry_version text,
 evidence_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 recorded_by text NOT NULL, checked_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL, request_hash text NOT NULL,
 UNIQUE(tenant_id, idempotency_key),
 CHECK (expected_artifact_digest ~ '^[a-fA-F0-9]{64}$'),
 CHECK (observed_artifact_digest ~ '^[a-fA-F0-9]{64}$')
);
CREATE INDEX IF NOT EXISTS idx_reconcile_evidence_recency
  ON decision_model_reconcile_evidence (tenant_id, model_id, target_environment, checked_at DESC);
DO $$ BEGIN
  EXECUTE 'DROP TRIGGER IF EXISTS trg_decision_model_reconcile_evidence_append_only ON decision_model_reconcile_evidence';
  EXECUTE 'CREATE TRIGGER trg_decision_model_reconcile_evidence_append_only BEFORE UPDATE OR DELETE ON decision_model_reconcile_evidence FOR EACH ROW EXECUTE FUNCTION decision_wx11_completion_append_only()';
END $$;
-- The runtime-work claim ledger (migration 016) must accept the two scheduled work types too,
-- so multi-replica single-owner leasing covers them like the other side-effecting work.
ALTER TABLE decision_model_runtime_work_claims
  DROP CONSTRAINT IF EXISTS decision_model_runtime_work_claims_work_type_check;
ALTER TABLE decision_model_runtime_work_claims
  ADD CONSTRAINT decision_model_runtime_work_claims_work_type_check
  CHECK (work_type IN ('post_activation_verification','rollout_apply','retraining_dispatch','monitoring_window','active_state_reconcile'));
