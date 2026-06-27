-- v101: Farm Operations Ledger — موازنة الموسم، الانحرافات، الربحية، وإسقاط ERP اختياري
-- توسعة آمنة خلف FEATURE_FARM_OPERATIONS_LEDGER. لا تضيف محاسبة مزدوجة ولا تفرض ERP.

BEGIN;

CREATE TABLE IF NOT EXISTS farm_season_budget_lines (
    budget_line_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    season_id TEXT REFERENCES farm_season_projects(season_id) ON DELETE CASCADE,
    stage TEXT NOT NULL DEFAULT 'whole_season',
    category TEXT NOT NULL,
    planned_quantity DOUBLE PRECISION,
    unit TEXT,
    planned_unit_cost DOUBLE PRECISION,
    planned_cost DOUBLE PRECISION NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'YER',
    source TEXT NOT NULL DEFAULT 'manual',
    editable BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS farm_revenue_records (
    revenue_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    season_id TEXT REFERENCES farm_season_projects(season_id) ON DELETE CASCADE,
    production_unit_id TEXT REFERENCES farm_production_units(production_unit_id) ON DELETE SET NULL,
    field_id TEXT,
    revenue_date DATE NOT NULL,
    product_name TEXT,
    quantity DOUBLE PRECISION,
    unit TEXT,
    unit_price DOUBLE PRECISION,
    amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'YER',
    source TEXT NOT NULL DEFAULT 'manual',
    notes TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS farm_indirect_cost_pools (
    pool_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    season_id TEXT REFERENCES farm_season_projects(season_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'YER',
    allocation_method TEXT NOT NULL DEFAULT 'per_hectare',
    notes TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_farm_budget_lines_tenant_season ON farm_season_budget_lines(tenant_id, season_id, stage, category);
CREATE INDEX IF NOT EXISTS idx_farm_revenue_records_tenant_season ON farm_revenue_records(tenant_id, season_id, revenue_date DESC);
CREATE INDEX IF NOT EXISTS idx_farm_indirect_cost_pools_tenant_season ON farm_indirect_cost_pools(tenant_id, season_id);

ALTER TABLE farm_season_budget_lines ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_season_budget_lines FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_revenue_records ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_revenue_records FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_indirect_cost_pools ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_indirect_cost_pools FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON farm_season_budget_lines;
CREATE POLICY tenant_isolation ON farm_season_budget_lines USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS tenant_isolation ON farm_revenue_records;
CREATE POLICY tenant_isolation ON farm_revenue_records USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS tenant_isolation ON farm_indirect_cost_pools;
CREATE POLICY tenant_isolation ON farm_indirect_cost_pools USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));

COMMENT ON TABLE farm_season_budget_lines IS 'بنود موازنة الموسم حسب المرحلة والتصنيف، قابلة للمقارنة مع سجل العمليات الفعلي.';
COMMENT ON TABLE farm_revenue_records IS 'إيرادات تشغيلية للموسم/الحقل لحساب الربحية داخل SAHOOL دون محاسبة مزدوجة.';
COMMENT ON TABLE farm_indirect_cost_pools IS 'مجمعات التكاليف غير المباشرة لتوزيعها تحليلياً على الوحدات الإنتاجية.';

COMMIT;
