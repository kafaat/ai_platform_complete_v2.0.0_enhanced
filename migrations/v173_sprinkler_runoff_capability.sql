-- M2.6 Sprinkler Package and Runoff Capability
BEGIN;
CREATE TABLE IF NOT EXISTS irrigation_sprinkler_packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL, machine_id UUID NOT NULL,
    name TEXT NOT NULL, application_mode TEXT NOT NULL CHECK (application_mode IN ('spray','lesa','lepa','rotator','moving_stream','bubbler')),
    regulator_pressure_bar NUMERIC CHECK (regulator_pressure_bar IS NULL OR regulator_pressure_bar > 0),
    tested_peak_application_mm_h NUMERIC NOT NULL CHECK (tested_peak_application_mm_h > 0),
    test_quality TEXT NOT NULL CHECK (test_quality IN ('estimated','measured','field_validated','certified')),
    certification_status TEXT NOT NULL DEFAULT 'draft' CHECK (certification_status IN ('draft','reviewed','certified','superseded','rejected')),
    test_digest CHAR(64) CHECK (test_digest IS NULL OR test_digest ~ '^[0-9a-f]{64}$'), evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (id, tenant_id),
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_sprinkler_zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL, package_id UUID NOT NULL,
    start_distance_m NUMERIC NOT NULL CHECK (start_distance_m >= 0), end_distance_m NUMERIC NOT NULL CHECK (end_distance_m > start_distance_m),
    nozzle_model TEXT, nozzle_diameter_mm NUMERIC CHECK (nozzle_diameter_mm IS NULL OR nozzle_diameter_mm > 0),
    design_flow_lps NUMERIC CHECK (design_flow_lps IS NULL OR design_flow_lps > 0), wetted_diameter_m NUMERIC CHECK (wetted_diameter_m IS NULL OR wetted_diameter_m > 0),
    spacing_m NUMERIC CHECK (spacing_m IS NULL OR spacing_m > 0), evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (id, tenant_id),
    FOREIGN KEY (package_id, tenant_id) REFERENCES irrigation_sprinkler_packages(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS canonical_sprinkler_runoff_capabilities (
    capability_id TEXT PRIMARY KEY, tenant_id UUID NOT NULL, project_id UUID NOT NULL, machine_id UUID NOT NULL, package_id UUID NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified','degraded','blocked')), operational_eligible BOOLEAN NOT NULL DEFAULT false,
    adjusted_peak_application_mm_h NUMERIC, infiltration_capacity_mm_h NUMERIC, runoff_safety_factor NUMERIC, maximum_safe_depth_mm_event NUMERIC,
    capability_digest CHAR(64) NOT NULL CHECK (capability_digest ~ '^[0-9a-f]{64}$'), payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (tenant_id, package_id, capability_digest),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (package_id, tenant_id) REFERENCES irrigation_sprinkler_packages(id, tenant_id) ON DELETE CASCADE
);

DO $$ DECLARE t TEXT; BEGIN FOREACH t IN ARRAY ARRAY['irrigation_sprinkler_packages','irrigation_sprinkler_zones','canonical_sprinkler_runoff_capabilities'] LOOP
EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t); EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t); EXECUTE format($p$CREATE POLICY tenant_isolation ON %I USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))$p$, t); END LOOP; END $$;
COMMIT;
