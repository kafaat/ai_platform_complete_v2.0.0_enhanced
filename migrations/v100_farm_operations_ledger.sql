-- v100: Farm Operations Ledger — سجلات تشغيل زراعية رقابية قابلة للمزامنة الاختيارية
-- لا تنفّذ محاسبة مزدوجة ولا تفرض ERP. المصدر التشغيلي القانوني داخل SAHOOL،
-- والـERP مجرّد إسقاط مالي اختياري لاحقاً عبر ERPProvider.

BEGIN;

CREATE TABLE IF NOT EXISTS farm_business_units (
    business_unit_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    unit_type TEXT NOT NULL,
    parent_id TEXT REFERENCES farm_business_units(business_unit_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code)
);

CREATE TABLE IF NOT EXISTS farm_production_units (
    production_unit_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    business_unit_id TEXT REFERENCES farm_business_units(business_unit_id) ON DELETE SET NULL,
    farm_id TEXT,
    field_id TEXT,
    unit_type TEXT NOT NULL,
    name TEXT NOT NULL,
    geometry JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS farm_season_projects (
    season_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    business_unit_id TEXT REFERENCES farm_business_units(business_unit_id) ON DELETE SET NULL,
    farm_id TEXT,
    crop_id TEXT,
    name TEXT NOT NULL,
    season_year INTEGER,
    start_date DATE,
    end_date DATE,
    status TEXT NOT NULL DEFAULT 'planned',
    target_yield DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS farm_operation_ledger (
    operation_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    season_id TEXT REFERENCES farm_season_projects(season_id) ON DELETE SET NULL,
    production_unit_id TEXT REFERENCES farm_production_units(production_unit_id) ON DELETE SET NULL,
    farm_id TEXT,
    field_id TEXT,
    operation_type TEXT NOT NULL,
    operation_date DATE NOT NULL,
    execution_mode TEXT NOT NULL DEFAULT 'self',
    contractor_id TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    notes TEXT,
    cost_amount DOUBLE PRECISION,
    cost_category TEXT,
    currency TEXT NOT NULL DEFAULT 'YER',
    sync_status TEXT NOT NULL DEFAULT 'control_only',
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS farm_water_records (
    water_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    operation_id TEXT REFERENCES farm_operation_ledger(operation_id) ON DELETE CASCADE,
    record_date DATE NOT NULL,
    farm_id TEXT,
    field_id TEXT,
    well_id TEXT,
    pump_id TEXT,
    pivot_id TEXT,
    hours_operated DOUBLE PRECISION,
    water_volume_m3 DOUBLE PRECISION,
    measurement_method TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS farm_energy_records (
    energy_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    operation_id TEXT REFERENCES farm_operation_ledger(operation_id) ON DELETE CASCADE,
    record_date DATE NOT NULL,
    energy_source TEXT NOT NULL DEFAULT 'unknown',
    kwh DOUBLE PRECISION,
    diesel_liters DOUBLE PRECISION,
    hours_operated DOUBLE PRECISION,
    equipment_id TEXT,
    well_id TEXT,
    pivot_id TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS farm_equipment_records (
    equipment_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    operation_id TEXT REFERENCES farm_operation_ledger(operation_id) ON DELETE CASCADE,
    record_date DATE NOT NULL,
    equipment_id TEXT NOT NULL,
    operator_id TEXT,
    hours_worked DOUBLE PRECISION,
    fuel_liters DOUBLE PRECISION,
    maintenance_cost DOUBLE PRECISION,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS farm_labor_records (
    labor_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    operation_id TEXT REFERENCES farm_operation_ledger(operation_id) ON DELETE CASCADE,
    record_date DATE NOT NULL,
    worker_id TEXT,
    workers_count INTEGER,
    hours DOUBLE PRECISION,
    wage_amount DOUBLE PRECISION,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS farm_input_records (
    input_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    operation_id TEXT REFERENCES farm_operation_ledger(operation_id) ON DELETE CASCADE,
    record_date DATE NOT NULL,
    input_type TEXT NOT NULL,
    inventory_item_id TEXT,
    quantity DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL,
    estimated_cost DOUBLE PRECISION,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_farm_operation_ledger_tenant_date ON farm_operation_ledger(tenant_id, operation_date DESC);
CREATE INDEX IF NOT EXISTS idx_farm_operation_ledger_tenant_field ON farm_operation_ledger(tenant_id, field_id, operation_date DESC);
CREATE INDEX IF NOT EXISTS idx_farm_water_records_tenant_field ON farm_water_records(tenant_id, field_id, record_date DESC);
CREATE INDEX IF NOT EXISTS idx_farm_input_records_tenant_op ON farm_input_records(tenant_id, operation_id);

-- RLS موحّد على كل الجداول.
ALTER TABLE farm_business_units ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_business_units FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_production_units ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_production_units FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_season_projects ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_season_projects FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_operation_ledger ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_operation_ledger FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_water_records ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_water_records FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_energy_records ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_energy_records FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_equipment_records ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_equipment_records FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_labor_records ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_labor_records FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_input_records ENABLE ROW LEVEL SECURITY; ALTER TABLE farm_input_records FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON farm_business_units;
CREATE POLICY tenant_isolation ON farm_business_units USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS tenant_isolation ON farm_production_units;
CREATE POLICY tenant_isolation ON farm_production_units USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS tenant_isolation ON farm_season_projects;
CREATE POLICY tenant_isolation ON farm_season_projects USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS tenant_isolation ON farm_operation_ledger;
CREATE POLICY tenant_isolation ON farm_operation_ledger USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS tenant_isolation ON farm_water_records;
CREATE POLICY tenant_isolation ON farm_water_records USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS tenant_isolation ON farm_energy_records;
CREATE POLICY tenant_isolation ON farm_energy_records USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS tenant_isolation ON farm_equipment_records;
CREATE POLICY tenant_isolation ON farm_equipment_records USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS tenant_isolation ON farm_labor_records;
CREATE POLICY tenant_isolation ON farm_labor_records USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS tenant_isolation ON farm_input_records;
CREATE POLICY tenant_isolation ON farm_input_records USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::TEXT = current_setting('app.current_tenant', true));

COMMENT ON TABLE farm_operation_ledger IS 'دفتر العمليات الزراعية اليومي — سجلات رقابية وتشغيلية قابلة للتلخيص والمزامنة المالية الاختيارية، لا محاسبة مزدوجة.';

COMMIT;
