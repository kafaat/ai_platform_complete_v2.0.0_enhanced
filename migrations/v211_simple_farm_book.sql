-- v211: Simple Farm Book — cash/credit expenses, income, parties and settlements.
-- Extends the existing farm ledger; it is not an ERP and does not duplicate inventory.

BEGIN;

CREATE TABLE IF NOT EXISTS farm_ledger_parties (
    party_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    party_type TEXT NOT NULL CHECK (party_type IN ('supplier', 'customer', 'both')),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    phone TEXT,
    notes TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, party_id)
);

CREATE TABLE IF NOT EXISTS farm_ledger_entries (
    entry_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    client_operation_id TEXT NOT NULL,
    request_digest CHAR(64) NOT NULL,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('expense', 'income', 'payment')),
    direction TEXT NOT NULL CHECK (direction IN ('outflow', 'inflow')),
    payment_method TEXT NOT NULL CHECK (payment_method IN ('cash', 'credit')),
    category TEXT NOT NULL,
    amount NUMERIC(18,2) NOT NULL CHECK (amount > 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'YER'
        CHECK (currency = upper(currency) AND length(currency) = 3),
    occurred_on DATE NOT NULL,
    farm_id TEXT,
    field_id TEXT,
    season_id TEXT,
    party_id TEXT,
    settles_entry_id TEXT,
    quantity NUMERIC(18,3) CHECK (quantity IS NULL OR quantity > 0),
    unit TEXT,
    description TEXT,
    receipt_document_id VARCHAR(50) REFERENCES documents(doc_id) ON DELETE SET NULL,
    source TEXT NOT NULL DEFAULT 'manual_mobile',
    sync_status TEXT NOT NULL DEFAULT 'synced'
        CHECK (sync_status IN ('pending', 'synced', 'conflict')),
    reverses_entry_id TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, client_operation_id),
    UNIQUE (tenant_id, entry_id),
    FOREIGN KEY (tenant_id, party_id)
        REFERENCES farm_ledger_parties(tenant_id, party_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, settles_entry_id)
        REFERENCES farm_ledger_entries(tenant_id, entry_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, reverses_entry_id)
        REFERENCES farm_ledger_entries(tenant_id, entry_id) ON DELETE RESTRICT,
    CHECK (
        (entry_type = 'expense' AND direction = 'outflow') OR
        (entry_type = 'income' AND direction = 'inflow') OR
        (entry_type = 'payment' AND party_id IS NOT NULL AND settles_entry_id IS NOT NULL)
    ),
    CHECK (entry_type <> 'payment' OR payment_method = 'cash'),
    CHECK (payment_method <> 'credit' OR party_id IS NOT NULL),
    CHECK (settles_entry_id IS NULL OR settles_entry_id <> entry_id),
    CHECK (reverses_entry_id IS NULL OR reverses_entry_id <> entry_id)
);

CREATE INDEX IF NOT EXISTS ix_farm_ledger_entries_tenant_date
    ON farm_ledger_entries (tenant_id, occurred_on DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_farm_ledger_entries_field_season
    ON farm_ledger_entries (tenant_id, field_id, season_id, occurred_on DESC);
CREATE INDEX IF NOT EXISTS ix_farm_ledger_entries_party
    ON farm_ledger_entries (tenant_id, party_id, occurred_on DESC);
CREATE INDEX IF NOT EXISTS ix_farm_ledger_entries_settlement
    ON farm_ledger_entries (tenant_id, settles_entry_id)
    WHERE settles_entry_id IS NOT NULL;

ALTER TABLE farm_ledger_parties ENABLE ROW LEVEL SECURITY;
ALTER TABLE farm_ledger_parties FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_ledger_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE farm_ledger_entries FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON farm_ledger_parties;
CREATE POLICY tenant_isolation ON farm_ledger_parties
USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''));

DROP POLICY IF EXISTS tenant_isolation ON farm_ledger_entries;
CREATE POLICY tenant_isolation ON farm_ledger_entries
USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''));

CREATE OR REPLACE FUNCTION sahool_simple_farm_book_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'simple farm book entries are append-only; add a reversing entry';
END $$;

DROP TRIGGER IF EXISTS trg_farm_ledger_entries_immutable ON farm_ledger_entries;
CREATE TRIGGER trg_farm_ledger_entries_immutable
BEFORE UPDATE OR DELETE ON farm_ledger_entries
FOR EACH ROW EXECUTE FUNCTION sahool_simple_farm_book_immutable();

COMMENT ON TABLE farm_ledger_parties IS
    'Simple farmer-facing suppliers/customers; operational identity, not ERP master data.';
COMMENT ON TABLE farm_ledger_entries IS
    'Append-only simple cash/credit farm book. Corrections use reverses_entry_id.';

COMMIT;
