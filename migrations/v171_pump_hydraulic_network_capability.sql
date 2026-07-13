-- M2.4 Pump and Hydraulic Network Capability
BEGIN;

CREATE TABLE IF NOT EXISTS irrigation_pump_curve_points (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    pump_id UUID NOT NULL,
    sequence_no INTEGER NOT NULL CHECK (sequence_no >= 0),
    flow_lps NUMERIC NOT NULL CHECK (flow_lps >= 0),
    head_m NUMERIC NOT NULL CHECK (head_m >= 0),
    efficiency NUMERIC CHECK (efficiency IS NULL OR efficiency > 0 AND efficiency <= 1),
    shaft_power_kw NUMERIC CHECK (shaft_power_kw IS NULL OR shaft_power_kw >= 0),
    certification_status TEXT NOT NULL DEFAULT 'draft' CHECK (certification_status IN ('draft','reviewed','certified','superseded','rejected')),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    UNIQUE (tenant_id, pump_id, sequence_no),
    UNIQUE (tenant_id, pump_id, flow_lps),
    FOREIGN KEY (pump_id, tenant_id) REFERENCES irrigation_pumps(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_hydraulic_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    asset_ref TEXT,
    node_type TEXT NOT NULL CHECK (node_type IN ('source','pump','junction','filter','valve','machine_inlet','zone','reservoir')),
    elevation_m NUMERIC NOT NULL,
    required_pressure_bar NUMERIC CHECK (required_pressure_bar IS NULL OR required_pressure_bar >= 0),
    certification_status TEXT NOT NULL DEFAULT 'draft' CHECK (certification_status IN ('draft','reviewed','certified','superseded','rejected')),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_hydraulic_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    from_node_id UUID NOT NULL,
    to_node_id UUID NOT NULL,
    length_m NUMERIC NOT NULL CHECK (length_m > 0),
    nominal_diameter_mm NUMERIC,
    internal_diameter_mm NUMERIC NOT NULL CHECK (internal_diameter_mm > 0),
    material TEXT NOT NULL,
    absolute_roughness_mm NUMERIC NOT NULL CHECK (absolute_roughness_mm >= 0),
    pressure_rating_bar NUMERIC NOT NULL CHECK (pressure_rating_bar > 0),
    minor_loss_k NUMERIC NOT NULL DEFAULT 0 CHECK (minor_loss_k >= 0),
    maximum_velocity_m_s NUMERIC NOT NULL DEFAULT 2.5 CHECK (maximum_velocity_m_s > 0),
    certification_status TEXT NOT NULL DEFAULT 'draft' CHECK (certification_status IN ('draft','reviewed','certified','superseded','rejected')),
    segment_digest CHAR(64) CHECK (segment_digest IS NULL OR segment_digest ~ '^[0-9a-f]{64}$'),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (from_node_id, tenant_id) REFERENCES irrigation_hydraulic_nodes(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (to_node_id, tenant_id) REFERENCES irrigation_hydraulic_nodes(id, tenant_id) ON DELETE CASCADE,
    CHECK (from_node_id <> to_node_id)
);

CREATE TABLE IF NOT EXISTS canonical_hydraulic_capabilities (
    capability_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    well_id UUID NOT NULL,
    pump_id UUID NOT NULL,
    target_asset_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified','degraded','blocked')),
    operational_eligible BOOLEAN NOT NULL DEFAULT false,
    maximum_deliverable_flow_lps NUMERIC,
    required_tdh_m NUMERIC,
    terminal_pressure_bar NUMERIC,
    specific_energy_kwh_m3 NUMERIC,
    capability_digest CHAR(64) NOT NULL CHECK (capability_digest ~ '^[0-9a-f]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, pump_id, target_asset_id, capability_digest),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (well_id, tenant_id) REFERENCES irrigation_wells(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (pump_id, tenant_id) REFERENCES irrigation_pumps(id, tenant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pump_curve_points ON irrigation_pump_curve_points (tenant_id, pump_id, flow_lps);
CREATE INDEX IF NOT EXISTS idx_hydraulic_segments_project ON irrigation_hydraulic_segments (tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_hydraulic_capabilities_latest ON canonical_hydraulic_capabilities (tenant_id, pump_id, created_at DESC);

DO $$ DECLARE t TEXT; BEGIN
  FOREACH t IN ARRAY ARRAY['irrigation_pump_curve_points','irrigation_hydraulic_nodes','irrigation_hydraulic_segments','canonical_hydraulic_capabilities'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON %I USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')) WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))$p$, t);
  END LOOP;
END $$;
COMMIT;
