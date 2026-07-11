-- WX-11.2 — immutable evaluation run + candidate artifact registration.
-- No training, no promotion, no active-model mutation.
CREATE TABLE IF NOT EXISTS decision_model_evaluation_runs (
  evaluation_run_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  model_id text NOT NULL,
  feature_set_id text NULL,
  dataset_fingerprint text NOT NULL,
  dataset_count integer NOT NULL,
  evaluator_version text NOT NULL,
  baseline_metrics jsonb NOT NULL,
  candidate_metrics jsonb NOT NULL,
  candidate_artifact_uri text NOT NULL,
  candidate_artifact_digest text NOT NULL,
  artifact_format text NOT NULL,
  evaluation_state text NOT NULL DEFAULT 'evaluated',
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  evaluated_by text NOT NULL,
  evaluated_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT ck_eval_dataset_count CHECK (dataset_count > 0),
  CONSTRAINT ck_eval_state CHECK (evaluation_state = 'evaluated'),
  CONSTRAINT ck_eval_digest CHECK (candidate_artifact_digest ~ '^[a-fA-F0-9]{64}$')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_model_eval_idempotency
  ON decision_model_evaluation_runs (tenant_id, idempotency_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_model_eval_artifact_digest
  ON decision_model_evaluation_runs (tenant_id, candidate_artifact_digest);
CREATE INDEX IF NOT EXISTS idx_model_eval_model_time
  ON decision_model_evaluation_runs (tenant_id, model_id, evaluated_at DESC);

CREATE OR REPLACE FUNCTION decision_model_evaluation_append_only()
RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'model evaluation run is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_decision_model_evaluation_append_only ON decision_model_evaluation_runs;
CREATE TRIGGER trg_decision_model_evaluation_append_only
  BEFORE UPDATE OR DELETE ON decision_model_evaluation_runs
  FOR EACH ROW EXECUTE FUNCTION decision_model_evaluation_append_only();
