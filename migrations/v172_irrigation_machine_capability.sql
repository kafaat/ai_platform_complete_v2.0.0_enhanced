-- M2.5 Irrigation Machine Engineering Capability
BEGIN;
ALTER TABLE irrigation_machines
    ADD COLUMN IF NOT EXISTS effective_area_ha NUMERIC CHECK (effective_area_ha IS NULL OR effective_area_ha > 0),
    ADD COLUMN IF NOT EXISTS full_cycle_hours NUMERIC CHECK (full_cycle_hours IS NULL OR full_cycle_hours > 0),
    ADD COLUMN IF NOT EXISTS minimum_speed_percent NUMERIC CHECK (minimum_speed_percent IS NULL OR minimum_speed_percent > 0 AND minimum_speed_percent <= 100),
    ADD COLUMN IF NOT EXISTS maximum_speed_percent NUMERIC CHECK (maximum_speed_percent IS NULL OR maximum_speed_percent > 0 AND maximum_speed_percent <= 100),
    ADD COLUMN IF NOT EXISTS certification_status TEXT NOT NULL DEFAULT 'draft' CHECK (certification_status IN ('draft','reviewed','certified','superseded','rejected')),
    ADD COLUMN IF NOT EXISTS certificate_digest CHAR(64) CHECK (certificate_digest IS NULL OR certificate_digest ~ '^[0-9a-f]{64}$');

CREATE TABLE IF NOT EXISTS irrigation_machine_spans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL, machine_id UUID NOT NULL,
    sequence_no INTEGER NOT NULL CHECK (sequence_no >= 1), length_m NUMERIC NOT NULL CHECK (length_m > 0),
    internal_diameter_mm NUMERIC NOT NULL CHECK (internal_diameter_mm > 0), tower_drive_type TEXT,
    motor_power_kw NUMERIC CHECK (motor_power_kw IS NULL OR motor_power_kw >= 0), gearbox_ratio NUMERIC CHECK (gearbox_ratio IS NULL OR gearbox_ratio > 0),
    tire_size TEXT, evidence JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id), UNIQUE (tenant_id, machine_id, sequence_no),
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS canonical_irrigation_machine_capabilities (
    capability_id TEXT PRIMARY KEY, tenant_id UUID NOT NULL, project_id UUID NOT NULL, machine_id UUID NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified','degraded','blocked')), operational_eligible BOOLEAN NOT NULL DEFAULT false,
    effective_area_ha NUMERIC, application_rate_mm_day NUMERIC, depth_per_full_cycle_mm NUMERIC, maximum_daily_depth_mm NUMERIC,
    capability_digest CHAR(64) NOT NULL CHECK (capability_digest ~ '^[0-9a-f]{64}$'), payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (tenant_id, machine_id, capability_digest),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id) ON DELETE CASCADE
);

DO $$ DECLARE t TEXT; BEGIN FOREACH t IN ARRAY ARRAY['irrigation_machine_spans','canonical_irrigation_machine_capabilities'] LOOP
EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t); EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t); EXECUTE format($p$CREATE POLICY tenant_isolation ON %I USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))$p$, t); END LOOP; END $$;
COMMIT;
