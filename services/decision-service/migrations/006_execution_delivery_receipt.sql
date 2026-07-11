-- WX-10.11b — execution adapter delivery claim + terminal receipt.
-- Additive/idempotent. Decision-service owns delivery state and immutable receipt evidence;
-- protocol-specific task/equipment adapters remain downstream service owners.

ALTER TABLE decision_execution_requests
  DROP CONSTRAINT IF EXISTS ck_execution_request_status;
ALTER TABLE decision_execution_requests
  ADD CONSTRAINT ck_execution_request_status
  CHECK (status IN ('queued','delivering','accepted','failed'));

CREATE TABLE IF NOT EXISTS decision_execution_delivery_attempts (
  delivery_attempt_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  execution_request_id text NOT NULL,
  adapter_id text NOT NULL,
  adapter_kind text NOT NULL,
  delivery_token_hash text NOT NULL,
  claimed_at timestamptz NOT NULL DEFAULT now(),
  receipt_id text NULL,
  receipt_status text NULL,
  receipt_payload jsonb NULL,
  received_at timestamptz NULL,
  CONSTRAINT fk_delivery_request FOREIGN KEY (execution_request_id)
    REFERENCES decision_execution_requests(execution_request_id),
  CONSTRAINT ck_delivery_adapter_kind CHECK (adapter_kind IN ('task','equipment')),
  CONSTRAINT ck_delivery_adapter_id CHECK (length(btrim(adapter_id)) > 0),
  CONSTRAINT ck_delivery_receipt_status CHECK (receipt_status IS NULL OR receipt_status IN ('accepted','failed'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_attempt_tenant_request
  ON decision_execution_delivery_attempts (tenant_id, execution_request_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_attempt_tenant_receipt
  ON decision_execution_delivery_attempts (tenant_id, receipt_id) WHERE receipt_id IS NOT NULL;

CREATE OR REPLACE FUNCTION decision_execution_delivery_attempts_append_only()
RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'decision_execution_delivery_attempts is append-preserving';
  END IF;
  IF NEW.delivery_attempt_id <> OLD.delivery_attempt_id
     OR NEW.tenant_id <> OLD.tenant_id
     OR NEW.execution_request_id <> OLD.execution_request_id
     OR NEW.adapter_id <> OLD.adapter_id
     OR NEW.adapter_kind <> OLD.adapter_kind
     OR NEW.delivery_token_hash <> OLD.delivery_token_hash
     OR NEW.claimed_at <> OLD.claimed_at THEN
    RAISE EXCEPTION 'decision_execution_delivery_attempt identity is immutable';
  END IF;
  IF OLD.receipt_id IS NOT NULL THEN
    RAISE EXCEPTION 'decision_execution_delivery_attempt receipt is immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_delivery_attempt_append_only ON decision_execution_delivery_attempts;
CREATE TRIGGER trg_delivery_attempt_append_only
  BEFORE UPDATE OR DELETE ON decision_execution_delivery_attempts
  FOR EACH ROW EXECUTE FUNCTION decision_execution_delivery_attempts_append_only();
