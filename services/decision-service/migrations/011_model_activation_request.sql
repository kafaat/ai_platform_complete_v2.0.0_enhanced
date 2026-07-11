-- WX-11.4 — immutable registry activation request.
-- Converts an eligible promotion decision into a reviewable request only.
-- Never mutates a model registry alias, deployment, or active model pointer.
CREATE TABLE IF NOT EXISTS decision_model_activation_requests (
  activation_request_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  promotion_decision_id text NOT NULL,
  evaluation_run_id text NOT NULL,
  model_id text NOT NULL,
  feature_set_id text NULL,
  candidate_artifact_uri text NOT NULL,
  candidate_artifact_digest text NOT NULL,
  target_environment text NOT NULL,
  requested_state text NOT NULL DEFAULT 'pending_activation_approval',
  requested_by text NOT NULL,
  requested_at timestamptz NOT NULL DEFAULT now(),
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT fk_activation_request_promotion
    FOREIGN KEY (promotion_decision_id) REFERENCES decision_model_promotion_decisions(promotion_decision_id),
  CONSTRAINT ck_activation_request_state CHECK (requested_state = 'pending_activation_approval'),
  CONSTRAINT ck_activation_request_environment CHECK (target_environment IN ('staging','production')),
  CONSTRAINT ck_activation_request_digest CHECK (candidate_artifact_digest ~ '^[a-fA-F0-9]{64}$')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_model_activation_request_idempotency
  ON decision_model_activation_requests (tenant_id, idempotency_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_model_activation_request_promotion_environment
  ON decision_model_activation_requests (tenant_id, promotion_decision_id, target_environment);
CREATE INDEX IF NOT EXISTS idx_model_activation_request_queue
  ON decision_model_activation_requests (tenant_id, requested_state, requested_at ASC);

CREATE OR REPLACE FUNCTION decision_model_activation_request_append_only()
RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'model activation request is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_decision_model_activation_request_append_only ON decision_model_activation_requests;
CREATE TRIGGER trg_decision_model_activation_request_append_only
  BEFORE UPDATE OR DELETE ON decision_model_activation_requests
  FOR EACH ROW EXECUTE FUNCTION decision_model_activation_request_append_only();
