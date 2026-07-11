-- WX-11.5 — governed activation approval and registry command boundary.
-- Records an immutable approval/rejection and, only for approval, one queued alias-change command.
-- The command contains an explicit rollback pointer. No registry alias is mutated by this migration/service.
CREATE TABLE IF NOT EXISTS decision_model_activation_reviews (
  activation_review_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  activation_request_id text NOT NULL,
  review_decision text NOT NULL,
  review_reason text NULL,
  registry_alias text NULL,
  previous_artifact_uri text NULL,
  previous_artifact_digest text NULL,
  reviewed_by text NOT NULL,
  reviewed_at timestamptz NOT NULL DEFAULT now(),
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT fk_activation_review_request FOREIGN KEY (activation_request_id)
    REFERENCES decision_model_activation_requests(activation_request_id),
  CONSTRAINT ck_activation_review_decision CHECK (review_decision IN ('approved','rejected')),
  CONSTRAINT ck_activation_review_rejection_reason CHECK (review_decision <> 'rejected' OR length(trim(review_reason)) > 0),
  CONSTRAINT ck_activation_review_approval_pointer CHECK (
    review_decision <> 'approved' OR (
      length(trim(registry_alias)) > 0 AND length(trim(previous_artifact_uri)) > 0
      AND previous_artifact_digest ~ '^[a-fA-F0-9]{64}$'
    )
  )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_activation_review_request ON decision_model_activation_reviews (tenant_id, activation_request_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_activation_review_idempotency ON decision_model_activation_reviews (tenant_id, idempotency_key);

CREATE TABLE IF NOT EXISTS decision_model_registry_activation_commands (
  activation_command_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  activation_review_id text NOT NULL,
  activation_request_id text NOT NULL,
  model_id text NOT NULL,
  feature_set_id text NULL,
  target_environment text NOT NULL,
  registry_alias text NOT NULL,
  candidate_artifact_uri text NOT NULL,
  candidate_artifact_digest text NOT NULL,
  previous_artifact_uri text NOT NULL,
  previous_artifact_digest text NOT NULL,
  command_state text NOT NULL DEFAULT 'queued',
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT fk_activation_command_review FOREIGN KEY (activation_review_id)
    REFERENCES decision_model_activation_reviews(activation_review_id),
  CONSTRAINT fk_activation_command_request FOREIGN KEY (activation_request_id)
    REFERENCES decision_model_activation_requests(activation_request_id),
  CONSTRAINT ck_activation_command_state CHECK (command_state = 'queued'),
  CONSTRAINT ck_activation_command_environment CHECK (target_environment IN ('staging','production')),
  CONSTRAINT ck_activation_command_candidate_digest CHECK (candidate_artifact_digest ~ '^[a-fA-F0-9]{64}$'),
  CONSTRAINT ck_activation_command_previous_digest CHECK (previous_artifact_digest ~ '^[a-fA-F0-9]{64}$')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_activation_command_review ON decision_model_registry_activation_commands (tenant_id, activation_review_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_activation_command_request ON decision_model_registry_activation_commands (tenant_id, activation_request_id);
CREATE INDEX IF NOT EXISTS idx_activation_command_queue ON decision_model_registry_activation_commands (tenant_id, command_state, created_at ASC);

CREATE OR REPLACE FUNCTION decision_model_activation_review_append_only()
RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'model activation review is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_model_activation_review_append_only ON decision_model_activation_reviews;
CREATE TRIGGER trg_model_activation_review_append_only BEFORE UPDATE OR DELETE ON decision_model_activation_reviews
FOR EACH ROW EXECUTE FUNCTION decision_model_activation_review_append_only();

CREATE OR REPLACE FUNCTION decision_model_activation_command_append_only()
RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'model activation command is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_model_activation_command_append_only ON decision_model_registry_activation_commands;
CREATE TRIGGER trg_model_activation_command_append_only BEFORE UPDATE OR DELETE ON decision_model_registry_activation_commands
FOR EACH ROW EXECUTE FUNCTION decision_model_activation_command_append_only();
