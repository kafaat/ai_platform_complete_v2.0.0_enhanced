-- WX-10.12 — terminal execution verification -> authoritative outcome_record lineage.
-- Additive/idempotent. Reuses the canonical outcome_record table; no second outcome model.

ALTER TABLE outcome_record ADD COLUMN IF NOT EXISTS execution_request_id text NULL;
ALTER TABLE outcome_record ADD COLUMN IF NOT EXISTS dispatch_authorization_id text NULL;
ALTER TABLE outcome_record ADD COLUMN IF NOT EXISTS execution_plan_id text NULL;
ALTER TABLE outcome_record ADD COLUMN IF NOT EXISTS receipt_id text NULL;
ALTER TABLE outcome_record ADD COLUMN IF NOT EXISTS verification_state text NULL;
ALTER TABLE outcome_record ADD COLUMN IF NOT EXISTS evidence_snapshot_id text NULL;
ALTER TABLE outcome_record ADD COLUMN IF NOT EXISTS verified_by text NULL;
ALTER TABLE outcome_record ADD COLUMN IF NOT EXISTS verified_at timestamptz NULL;
ALTER TABLE outcome_record ADD COLUMN IF NOT EXISTS request_hash text NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_outcome_record_tenant_execution_request
  ON outcome_record (tenant_id, execution_request_id) WHERE execution_request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_outcome_record_tenant_verification
  ON outcome_record (tenant_id, verification_state, verified_at DESC)
  WHERE verification_state IS NOT NULL;

ALTER TABLE outcome_record DROP CONSTRAINT IF EXISTS ck_outcome_verification_state;
ALTER TABLE outcome_record ADD CONSTRAINT ck_outcome_verification_state
  CHECK (verification_state IS NULL OR verification_state IN ('verified_success','verified_failure'));

CREATE OR REPLACE FUNCTION outcome_record_execution_append_only()
RETURNS trigger AS $$
BEGIN
  IF OLD.execution_request_id IS NOT NULL THEN
    RAISE EXCEPTION 'verified execution outcome is immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_outcome_record_execution_append_only ON outcome_record;
CREATE TRIGGER trg_outcome_record_execution_append_only
  BEFORE UPDATE OR DELETE ON outcome_record
  FOR EACH ROW EXECUTE FUNCTION outcome_record_execution_append_only();
