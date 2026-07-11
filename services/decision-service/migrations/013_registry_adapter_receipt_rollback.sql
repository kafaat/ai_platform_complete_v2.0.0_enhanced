-- WX-11.6 — registry adapter claim, alias-change receipt, and rollback command boundary.
CREATE TABLE IF NOT EXISTS decision_model_registry_activation_claims (
  activation_claim_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  activation_command_id text NOT NULL,
  adapter_id text NOT NULL,
  delivery_token_hash text NOT NULL,
  claimed_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_registry_claim_command FOREIGN KEY (activation_command_id)
    REFERENCES decision_model_registry_activation_commands(activation_command_id),
  CONSTRAINT ck_registry_claim_token_hash CHECK (delivery_token_hash ~ '^[a-f0-9]{64}$')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_registry_claim_command ON decision_model_registry_activation_claims (tenant_id, activation_command_id);

CREATE TABLE IF NOT EXISTS decision_model_registry_activation_receipts (
  activation_receipt_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  activation_command_id text NOT NULL,
  activation_claim_id text NOT NULL,
  receipt_state text NOT NULL,
  active_artifact_uri text NULL,
  active_artifact_digest text NULL,
  registry_version text NULL,
  failure_reason text NULL,
  receipt_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  recorded_by text NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  CONSTRAINT fk_registry_receipt_command FOREIGN KEY (activation_command_id)
    REFERENCES decision_model_registry_activation_commands(activation_command_id),
  CONSTRAINT fk_registry_receipt_claim FOREIGN KEY (activation_claim_id)
    REFERENCES decision_model_registry_activation_claims(activation_claim_id),
  CONSTRAINT ck_registry_receipt_state CHECK (receipt_state IN ('activated','failed')),
  CONSTRAINT ck_registry_receipt_success CHECK (receipt_state <> 'activated' OR (length(trim(active_artifact_uri)) > 0 AND active_artifact_digest ~ '^[a-fA-F0-9]{64}$')),
  CONSTRAINT ck_registry_receipt_failure CHECK (receipt_state <> 'failed' OR length(trim(failure_reason)) > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_registry_receipt_command ON decision_model_registry_activation_receipts (tenant_id, activation_command_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_registry_receipt_idempotency ON decision_model_registry_activation_receipts (tenant_id, idempotency_key);

CREATE TABLE IF NOT EXISTS decision_model_registry_rollback_commands (
  rollback_command_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  activation_receipt_id text NOT NULL,
  activation_command_id text NOT NULL,
  registry_alias text NOT NULL,
  target_environment text NOT NULL,
  restore_artifact_uri text NOT NULL,
  restore_artifact_digest text NOT NULL,
  replace_artifact_uri text NOT NULL,
  replace_artifact_digest text NOT NULL,
  command_state text NOT NULL DEFAULT 'queued',
  requested_by text NOT NULL,
  requested_at timestamptz NOT NULL DEFAULT now(),
  reason text NOT NULL,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  CONSTRAINT fk_rollback_receipt FOREIGN KEY (activation_receipt_id)
    REFERENCES decision_model_registry_activation_receipts(activation_receipt_id),
  CONSTRAINT ck_rollback_state CHECK (command_state = 'queued'),
  CONSTRAINT ck_rollback_restore_digest CHECK (restore_artifact_digest ~ '^[a-fA-F0-9]{64}$'),
  CONSTRAINT ck_rollback_replace_digest CHECK (replace_artifact_digest ~ '^[a-fA-F0-9]{64}$')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_rollback_receipt ON decision_model_registry_rollback_commands (tenant_id, activation_receipt_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_rollback_idempotency ON decision_model_registry_rollback_commands (tenant_id, idempotency_key);

CREATE OR REPLACE FUNCTION decision_registry_wx116_append_only() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'registry activation evidence is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_registry_claim_append_only ON decision_model_registry_activation_claims;
CREATE TRIGGER trg_registry_claim_append_only BEFORE UPDATE OR DELETE ON decision_model_registry_activation_claims FOR EACH ROW EXECUTE FUNCTION decision_registry_wx116_append_only();
DROP TRIGGER IF EXISTS trg_registry_receipt_append_only ON decision_model_registry_activation_receipts;
CREATE TRIGGER trg_registry_receipt_append_only BEFORE UPDATE OR DELETE ON decision_model_registry_activation_receipts FOR EACH ROW EXECUTE FUNCTION decision_registry_wx116_append_only();
DROP TRIGGER IF EXISTS trg_registry_rollback_append_only ON decision_model_registry_rollback_commands;
CREATE TRIGGER trg_registry_rollback_append_only BEFORE UPDATE OR DELETE ON decision_model_registry_rollback_commands FOR EACH ROW EXECUTE FUNCTION decision_registry_wx116_append_only();
