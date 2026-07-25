-- v210 / S11: provider-neutral ERP reconciliation ledger over the existing projection outbox.

BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS uq_farm_erp_outbox_tenant_id
  ON farm_ledger_erp_projection_outbox(tenant_id, outbox_id);

CREATE TABLE IF NOT EXISTS erp_reconciliation_ledger (
    reconciliation_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    outbox_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    external_reference TEXT,
    status TEXT NOT NULL CHECK (status IN ('matched','difference','rejected')),
    expected_amount NUMERIC(18,2),
    actual_amount NUMERIC(18,2),
    currency CHAR(3),
    difference_amount NUMERIC(18,2) GENERATED ALWAYS AS
      (CASE WHEN expected_amount IS NULL OR actual_amount IS NULL
            THEN NULL ELSE actual_amount - expected_amount END) STORED,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(evidence) = 'object'),
    content_hash CHAR(64) NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    reconciled_by TEXT NOT NULL,
    reconciled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT erp_reconciliation_outbox_fk
      FOREIGN KEY (tenant_id, outbox_id)
      REFERENCES farm_ledger_erp_projection_outbox(tenant_id, outbox_id),
    CONSTRAINT erp_reconciliation_provider_idempotency
      UNIQUE (tenant_id, provider, provider_event_id)
);

CREATE INDEX IF NOT EXISTS idx_erp_reconciliation_outbox
  ON erp_reconciliation_ledger(tenant_id, outbox_id, reconciled_at DESC);

ALTER TABLE erp_reconciliation_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp_reconciliation_ledger FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS erp_reconciliation_tenant_isolation ON erp_reconciliation_ledger;
CREATE POLICY erp_reconciliation_tenant_isolation ON erp_reconciliation_ledger
  USING (
    tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
  )
  WITH CHECK (
    tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
  );

CREATE OR REPLACE FUNCTION prevent_erp_reconciliation_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'ERP reconciliation ledger is append-only';
END;
$$;
DROP TRIGGER IF EXISTS erp_reconciliation_append_only ON erp_reconciliation_ledger;
CREATE TRIGGER erp_reconciliation_append_only
BEFORE UPDATE OR DELETE ON erp_reconciliation_ledger
FOR EACH ROW EXECUTE FUNCTION prevent_erp_reconciliation_mutation();

COMMENT ON TABLE erp_reconciliation_ledger IS
  'S11 provider-neutral immutable reconciliation evidence; does not make ERP writes.';

COMMIT;
