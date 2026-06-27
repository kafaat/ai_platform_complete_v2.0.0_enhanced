-- v102: Farm Operations Ledger — closed-loop projections and sync outboxes
-- Safe extension behind feature flags. No ERP write and no inventory write by default.

BEGIN;

CREATE TABLE IF NOT EXISTS farm_ledger_inventory_projections (
    projection_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    season_id TEXT REFERENCES farm_season_projects(season_id) ON DELETE CASCADE,
    operation_id TEXT REFERENCES farm_operation_ledger(operation_id) ON DELETE CASCADE,
    resource_type TEXT NOT NULL,
    inventory_item_id TEXT,
    quantity DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL,
    estimated_cost DOUBLE PRECISION,
    direction TEXT NOT NULL DEFAULT 'outbound',
    posting_mode TEXT NOT NULL DEFAULT 'projection_only',
    status TEXT NOT NULL DEFAULT 'draft',
    disabled_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS farm_ledger_erp_projection_outbox (
    outbox_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    season_id TEXT REFERENCES farm_season_projects(season_id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'none',
    projection_type TEXT NOT NULL DEFAULT 'season_summary',
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    disabled_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS farm_ledger_economic_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    season_id TEXT REFERENCES farm_season_projects(season_id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    payload JSONB NOT NULL,
    canonical_write BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_farm_inventory_projection_tenant_season ON farm_ledger_inventory_projections(tenant_id, season_id, status);
CREATE INDEX IF NOT EXISTS idx_farm_erp_outbox_tenant_season ON farm_ledger_erp_projection_outbox(tenant_id, season_id, status);
CREATE INDEX IF NOT EXISTS idx_farm_economic_snapshots_tenant_season ON farm_ledger_economic_snapshots(tenant_id, season_id, snapshot_date DESC);

ALTER TABLE farm_ledger_inventory_projections ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_ledger_inventory_projections FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_ledger_erp_projection_outbox ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_ledger_erp_projection_outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_ledger_economic_snapshots ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_ledger_economic_snapshots FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON farm_ledger_inventory_projections;
CREATE POLICY tenant_isolation ON farm_ledger_inventory_projections USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS tenant_isolation ON farm_ledger_erp_projection_outbox;
CREATE POLICY tenant_isolation ON farm_ledger_erp_projection_outbox USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS tenant_isolation ON farm_ledger_economic_snapshots;
CREATE POLICY tenant_isolation ON farm_ledger_economic_snapshots USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));

COMMENT ON TABLE farm_ledger_inventory_projections IS 'إسقاطات خصم مخزون من سجلات المواد؛ projection_only افتراضياً ولا تكتب في inventory-service.';
COMMENT ON TABLE farm_ledger_erp_projection_outbox IS 'مسودة إسقاط مالي اختياري إلى ERPProvider؛ لا إرسال افتراضي.';
COMMENT ON TABLE farm_ledger_economic_snapshots IS 'لقطات حالة اقتصادية من Farm Ledger؛ لا تكتب في CanonicalFieldState إلا لاحقاً وبعلم صريح.';

COMMIT;
