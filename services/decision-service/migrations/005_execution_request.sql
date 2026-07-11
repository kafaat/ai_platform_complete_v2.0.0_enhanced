-- WX-10.11a — Authorized dispatch -> execution request boundary.
-- Additive/idempotent. Persists a dispatchable task/equipment request and receipt envelope;
-- physical delivery remains owned by downstream task/actuator adapters.

CREATE TABLE IF NOT EXISTS decision_execution_requests (
  execution_request_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  dispatch_authorization_id text NOT NULL,
  execution_plan_id text NOT NULL,
  decision_id text NOT NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  operation_type text NOT NULL,
  command_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'queued',
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  requested_by text NOT NULL,
  requested_at timestamptz NOT NULL DEFAULT now(),
  receipt_id text NULL,
  receipt_status text NULL,
  receipt_payload jsonb NULL,
  received_at timestamptz NULL,
  CONSTRAINT ck_execution_request_target CHECK (target_type IN ('task','equipment')),
  CONSTRAINT ck_execution_request_status CHECK (status IN ('queued','accepted','failed')),
  CONSTRAINT ck_execution_request_actor CHECK (length(btrim(requested_by)) > 0),
  CONSTRAINT ck_execution_request_target_id CHECK (length(btrim(target_id)) > 0),
  CONSTRAINT ck_execution_request_operation CHECK (length(btrim(operation_type)) > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_execution_request_tenant_auth
  ON decision_execution_requests (tenant_id, dispatch_authorization_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_execution_request_tenant_idem
  ON decision_execution_requests (tenant_id, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_execution_request_tenant_created
  ON decision_execution_requests (tenant_id, requested_at DESC);

CREATE OR REPLACE FUNCTION decision_execution_requests_immutable_identity()
RETURNS trigger AS $$
BEGIN
  IF NEW.execution_request_id <> OLD.execution_request_id
     OR NEW.tenant_id <> OLD.tenant_id
     OR NEW.dispatch_authorization_id <> OLD.dispatch_authorization_id
     OR NEW.execution_plan_id <> OLD.execution_plan_id
     OR NEW.decision_id <> OLD.decision_id
     OR NEW.target_type <> OLD.target_type
     OR NEW.target_id <> OLD.target_id
     OR NEW.operation_type <> OLD.operation_type
     OR NEW.command_payload <> OLD.command_payload
     OR NEW.idempotency_key <> OLD.idempotency_key
     OR NEW.request_hash <> OLD.request_hash
     OR NEW.requested_by <> OLD.requested_by
     OR NEW.requested_at <> OLD.requested_at THEN
    RAISE EXCEPTION 'decision_execution_requests identity is immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_decision_execution_requests_immutable_identity ON decision_execution_requests;
CREATE TRIGGER trg_decision_execution_requests_immutable_identity
  BEFORE UPDATE ON decision_execution_requests
  FOR EACH ROW EXECUTE FUNCTION decision_execution_requests_immutable_identity();

CREATE OR REPLACE FUNCTION decision_execution_requests_no_delete()
RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'decision_execution_requests is append-preserving'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_decision_execution_requests_no_delete ON decision_execution_requests;
CREATE TRIGGER trg_decision_execution_requests_no_delete
  BEFORE DELETE ON decision_execution_requests
  FOR EACH ROW EXECUTE FUNCTION decision_execution_requests_no_delete();
