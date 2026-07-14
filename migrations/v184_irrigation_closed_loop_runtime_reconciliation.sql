-- v184: durable idempotent reconciliation from verified as-applied truth into water_ledger.
BEGIN;

ALTER TABLE as_applied_irrigation_runs
  ADD COLUMN IF NOT EXISTS planned_start_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS planned_end_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS planned_volume_m3 DOUBLE PRECISION;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_as_applied_plan_window_v184') THEN
    ALTER TABLE as_applied_irrigation_runs ADD CONSTRAINT chk_as_applied_plan_window_v184
      CHECK (planned_start_at IS NULL OR planned_end_at IS NULL OR planned_end_at > planned_start_at) NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_as_applied_plan_volume_v184') THEN
    ALTER TABLE as_applied_irrigation_runs ADD CONSTRAINT chk_as_applied_plan_volume_v184
      CHECK (planned_volume_m3 IS NULL OR planned_volume_m3 > 0) NOT VALID;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS irrigation_water_ledger_reconciliations (
    reconciliation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    run_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    execution_plan_id TEXT NOT NULL,
    as_applied_digest CHAR(64) NOT NULL CHECK (as_applied_digest ~ '^[0-9a-f]{64}$'),
    ledger_event_digest CHAR(64) NOT NULL CHECK (ledger_event_digest ~ '^[0-9a-f]{64}$'),
    ledger_date DATE NOT NULL,
    applied_depth_mm DOUBLE PRECISION NOT NULL CHECK (applied_depth_mm >= 0),
    applied_volume_m3 DOUBLE PRECISION NOT NULL CHECK (applied_volume_m3 >= 0),
    depletion_before_mm DOUBLE PRECISION,
    depletion_after_mm DOUBLE PRECISION,
    status TEXT NOT NULL CHECK (status IN ('persisted','reconciled','blocked')),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reconciled_at TIMESTAMPTZ,
    UNIQUE (tenant_id, as_applied_digest),
    UNIQUE (tenant_id, ledger_event_digest),
    UNIQUE (tenant_id, run_id),
    FOREIGN KEY (tenant_id, run_id)
      REFERENCES as_applied_irrigation_runs(tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_irrigation_ledger_reconciliation_field
  ON irrigation_water_ledger_reconciliations(tenant_id, field_id, ledger_date DESC);

ALTER TABLE irrigation_water_ledger_reconciliations ENABLE ROW LEVEL SECURITY;
ALTER TABLE irrigation_water_ledger_reconciliations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON irrigation_water_ledger_reconciliations;
CREATE POLICY tenant_isolation ON irrigation_water_ledger_reconciliations
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

COMMIT;
