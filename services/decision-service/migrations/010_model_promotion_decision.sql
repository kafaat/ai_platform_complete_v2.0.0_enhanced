-- WX-11.3 — immutable governed candidate promotion decision.
-- Records policy evaluation only; never mutates an active model or registry alias.
CREATE TABLE IF NOT EXISTS decision_model_promotion_decisions (
  promotion_decision_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  evaluation_run_id text NOT NULL,
  model_id text NOT NULL,
  feature_set_id text NULL,
  policy_version text NOT NULL,
  policy_snapshot jsonb NOT NULL,
  metric_deltas jsonb NOT NULL,
  decision_state text NOT NULL,
  decision_reason text NOT NULL,
  candidate_artifact_uri text NOT NULL,
  candidate_artifact_digest text NOT NULL,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  decided_by text NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT fk_model_promotion_evaluation
    FOREIGN KEY (evaluation_run_id) REFERENCES decision_model_evaluation_runs(evaluation_run_id),
  CONSTRAINT ck_model_promotion_state CHECK (decision_state IN ('promotion_eligible','promotion_rejected')),
  CONSTRAINT ck_model_promotion_digest CHECK (candidate_artifact_digest ~ '^[a-fA-F0-9]{64}$')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_model_promotion_idempotency
  ON decision_model_promotion_decisions (tenant_id, idempotency_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_model_promotion_evaluation
  ON decision_model_promotion_decisions (tenant_id, evaluation_run_id);
CREATE INDEX IF NOT EXISTS idx_model_promotion_model_time
  ON decision_model_promotion_decisions (tenant_id, model_id, decided_at DESC);

CREATE OR REPLACE FUNCTION decision_model_promotion_append_only()
RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'model promotion decision is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_decision_model_promotion_append_only ON decision_model_promotion_decisions;
CREATE TRIGGER trg_decision_model_promotion_append_only
  BEFORE UPDATE OR DELETE ON decision_model_promotion_decisions
  FOR EACH ROW EXECUTE FUNCTION decision_model_promotion_append_only();
