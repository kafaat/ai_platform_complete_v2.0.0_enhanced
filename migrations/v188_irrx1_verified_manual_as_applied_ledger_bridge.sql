-- IRR-X1.3 independently verified manual as-applied truth and idempotent ledger bridge.
ALTER TABLE irrigation_manual_executions
    ADD COLUMN IF NOT EXISTS verification jsonb,
    ADD COLUMN IF NOT EXISTS verification_digest char(64),
    ADD COLUMN IF NOT EXISTS verified_by text,
    ADD COLUMN IF NOT EXISTS ledger_event_digest char(64);

CREATE UNIQUE INDEX IF NOT EXISTS irrigation_manual_exec_verification_digest_uq
    ON irrigation_manual_executions (tenant_id, verification_digest)
    WHERE verification_digest IS NOT NULL;

CREATE TABLE IF NOT EXISTS irrigation_manual_ledger_reconciliations (
    reconciliation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    execution_id uuid NOT NULL REFERENCES irrigation_manual_executions(execution_id),
    field_id text NOT NULL,
    season_id text NOT NULL,
    ledger_date date NOT NULL,
    applied_depth_mm numeric NOT NULL CHECK (applied_depth_mm > 0),
    applied_volume_m3 numeric NOT NULL CHECK (applied_volume_m3 > 0),
    depletion_before_mm numeric,
    depletion_after_mm numeric,
    as_applied_digest char(64) NOT NULL,
    verification_digest char(64) NOT NULL,
    ledger_event_digest char(64) NOT NULL,
    status text NOT NULL DEFAULT 'reconciled' CHECK (status IN ('reconciled')),
    payload jsonb NOT NULL,
    reconciled_by text NOT NULL,
    reconciled_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, execution_id),
    UNIQUE (tenant_id, ledger_event_digest)
);

ALTER TABLE irrigation_manual_ledger_reconciliations ENABLE ROW LEVEL SECURITY;
ALTER TABLE irrigation_manual_ledger_reconciliations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS irrigation_manual_ledger_reconciliations_tenant ON irrigation_manual_ledger_reconciliations;
CREATE POLICY irrigation_manual_ledger_reconciliations_tenant ON irrigation_manual_ledger_reconciliations
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE OR REPLACE FUNCTION prevent_manual_ledger_reconciliation_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'manual ledger reconciliations are append-only'; END; $$;
DROP TRIGGER IF EXISTS manual_ledger_reconciliations_append_only ON irrigation_manual_ledger_reconciliations;
CREATE TRIGGER manual_ledger_reconciliations_append_only
BEFORE UPDATE OR DELETE ON irrigation_manual_ledger_reconciliations
FOR EACH ROW EXECUTE FUNCTION prevent_manual_ledger_reconciliation_mutation();
