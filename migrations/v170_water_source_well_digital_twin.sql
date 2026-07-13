-- M2.3 Water Source and Well Digital Twin
-- Immutable pumping evidence, measurements, quality, allocations, and canonical capability snapshots.
BEGIN;

ALTER TABLE irrigation_water_sources
    ADD COLUMN IF NOT EXISTS maximum_allowed_ec_ds_m NUMERIC CHECK (maximum_allowed_ec_ds_m IS NULL OR maximum_allowed_ec_ds_m >= 0);
ALTER TABLE irrigation_wells
    ADD COLUMN IF NOT EXISTS maximum_drawdown_m NUMERIC CHECK (maximum_drawdown_m IS NULL OR maximum_drawdown_m > 0),
    ADD COLUMN IF NOT EXISTS minimum_rest_hours NUMERIC NOT NULL DEFAULT 0 CHECK (minimum_rest_hours >= 0);

CREATE TABLE IF NOT EXISTS irrigation_well_pumping_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    well_id UUID NOT NULL,
    tested_at TIMESTAMPTZ NOT NULL,
    duration_hours NUMERIC NOT NULL CHECK (duration_hours > 0),
    tested_flow_lps NUMERIC NOT NULL CHECK (tested_flow_lps > 0),
    initial_static_level_m NUMERIC NOT NULL CHECK (initial_static_level_m >= 0),
    final_dynamic_level_m NUMERIC NOT NULL CHECK (final_dynamic_level_m > initial_static_level_m),
    drawdown_m NUMERIC GENERATED ALWAYS AS (final_dynamic_level_m - initial_static_level_m) STORED,
    specific_capacity_lps_per_m NUMERIC GENERATED ALWAYS AS (tested_flow_lps / NULLIF(final_dynamic_level_m - initial_static_level_m, 0)) STORED,
    recovery_rate_m_h NUMERIC CHECK (recovery_rate_m_h IS NULL OR recovery_rate_m_h > 0),
    recommended_sustainable_flow_lps NUMERIC NOT NULL CHECK (recommended_sustainable_flow_lps > 0 AND recommended_sustainable_flow_lps <= tested_flow_lps),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','reviewed','certified','superseded','rejected')),
    method TEXT NOT NULL DEFAULT 'constant_rate',
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    certified_by TEXT,
    certified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (well_id, tenant_id) REFERENCES irrigation_wells(id, tenant_id) ON DELETE CASCADE,
    CHECK ((status = 'certified' AND certified_at IS NOT NULL AND certified_by IS NOT NULL) OR status <> 'certified')
);

CREATE TABLE IF NOT EXISTS irrigation_well_measurements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    well_id UUID NOT NULL,
    measured_at TIMESTAMPTZ NOT NULL,
    static_level_m NUMERIC NOT NULL CHECK (static_level_m >= 0),
    dynamic_level_m NUMERIC NOT NULL CHECK (dynamic_level_m > static_level_m),
    measured_flow_lps NUMERIC CHECK (measured_flow_lps IS NULL OR measured_flow_lps >= 0),
    runtime_hours NUMERIC CHECK (runtime_hours IS NULL OR runtime_hours >= 0),
    source TEXT NOT NULL CHECK (source IN ('manual','sensor','scada','controller','commissioning')),
    quality TEXT NOT NULL DEFAULT 'measured' CHECK (quality IN ('estimated','measured','field_validated','certified')),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    UNIQUE (tenant_id, well_id, measured_at),
    FOREIGN KEY (well_id, tenant_id) REFERENCES irrigation_wells(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_water_quality_samples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    water_source_id UUID NOT NULL,
    sampled_at TIMESTAMPTZ NOT NULL,
    ec_ds_m NUMERIC CHECK (ec_ds_m IS NULL OR ec_ds_m >= 0),
    ph NUMERIC CHECK (ph IS NULL OR ph BETWEEN 0 AND 14),
    sar NUMERIC CHECK (sar IS NULL OR sar >= 0),
    chloride_mg_l NUMERIC CHECK (chloride_mg_l IS NULL OR chloride_mg_l >= 0),
    boron_mg_l NUMERIC CHECK (boron_mg_l IS NULL OR boron_mg_l >= 0),
    laboratory TEXT,
    quality TEXT NOT NULL DEFAULT 'measured' CHECK (quality IN ('estimated','measured','field_validated','certified')),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (water_source_id, tenant_id) REFERENCES irrigation_water_sources(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_water_allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    water_source_id UUID NOT NULL,
    season_id TEXT NOT NULL,
    valid_date DATE NOT NULL,
    daily_allocation_m3 NUMERIC NOT NULL CHECK (daily_allocation_m3 >= 0),
    daily_used_m3 NUMERIC NOT NULL DEFAULT 0 CHECK (daily_used_m3 >= 0 AND daily_used_m3 <= daily_allocation_m3),
    seasonal_allocation_m3 NUMERIC CHECK (seasonal_allocation_m3 IS NULL OR seasonal_allocation_m3 >= 0),
    seasonal_used_m3 NUMERIC NOT NULL DEFAULT 0 CHECK (seasonal_used_m3 >= 0),
    source TEXT NOT NULL DEFAULT 'policy',
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    UNIQUE (tenant_id, water_source_id, season_id, valid_date),
    FOREIGN KEY (water_source_id, tenant_id) REFERENCES irrigation_water_sources(id, tenant_id) ON DELETE CASCADE,
    CHECK (seasonal_allocation_m3 IS NULL OR seasonal_used_m3 <= seasonal_allocation_m3)
);

CREATE TABLE IF NOT EXISTS canonical_well_capabilities (
    capability_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    water_source_id UUID NOT NULL,
    well_id UUID NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL CHECK (status IN ('verified','degraded','blocked')),
    operational_eligible BOOLEAN NOT NULL DEFAULT false,
    maximum_flow_lps NUMERIC,
    remaining_daily_volume_m3 NUMERIC,
    remaining_seasonal_volume_m3 NUMERIC,
    drawdown_m NUMERIC,
    specific_capacity_lps_per_m NUMERIC,
    water_ec_ds_m NUMERIC,
    capability_digest CHAR(64) NOT NULL CHECK (capability_digest ~ '^[0-9a-f]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, well_id, capability_digest),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (water_source_id, tenant_id) REFERENCES irrigation_water_sources(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (well_id, tenant_id) REFERENCES irrigation_wells(id, tenant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_well_pumping_tests_latest ON irrigation_well_pumping_tests (tenant_id, well_id, tested_at DESC);
CREATE INDEX IF NOT EXISTS idx_well_measurements_latest ON irrigation_well_measurements (tenant_id, well_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_water_quality_latest ON irrigation_water_quality_samples (tenant_id, water_source_id, sampled_at DESC);
CREATE INDEX IF NOT EXISTS idx_water_allocations_lookup ON irrigation_water_allocations (tenant_id, water_source_id, season_id, valid_date DESC);
CREATE INDEX IF NOT EXISTS idx_well_capabilities_latest ON canonical_well_capabilities (tenant_id, well_id, generated_at DESC);

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'irrigation_well_pumping_tests','irrigation_well_measurements','irrigation_water_quality_samples',
    'irrigation_water_allocations','canonical_well_capabilities'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON %I
      USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
      WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))$p$, t);
  END LOOP;
END $$;

COMMENT ON TABLE canonical_well_capabilities IS 'Immutable M2.3 governed well capability snapshots for MPC and engineering feasibility.';
COMMENT ON COLUMN canonical_well_capabilities.capability_digest IS 'Full SHA-256 over all material source, test, measurement, allocation, and quality inputs.';
COMMIT;
