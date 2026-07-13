-- M2.8 Unified Irrigation Capability Graph
BEGIN;

CREATE TABLE IF NOT EXISTS canonical_irrigation_capability_graphs (
    capability_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    well_id UUID NOT NULL,
    pump_id UUID NOT NULL,
    machine_id UUID NOT NULL,
    controller_id UUID NOT NULL,
    energy_system_id UUID NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified','degraded','blocked')),
    operational_eligible BOOLEAN NOT NULL DEFAULT false,
    weakest_link TEXT CHECK (weakest_link IS NULL OR weakest_link IN ('well','hydraulic','machine','sprinkler','energy','controller')),
    maximum_flow_lps NUMERIC NOT NULL CHECK (maximum_flow_lps >= 0),
    maximum_daily_depth_mm NUMERIC NOT NULL CHECK (maximum_daily_depth_mm >= 0),
    maximum_safe_depth_mm_event NUMERIC NOT NULL CHECK (maximum_safe_depth_mm_event >= 0),
    terminal_pressure_bar NUMERIC NOT NULL CHECK (terminal_pressure_bar >= 0),
    specific_energy_kwh_m3 NUMERIC CHECK (specific_energy_kwh_m3 IS NULL OR specific_energy_kwh_m3 >= 0),
    capability_digest CHAR(64) NOT NULL CHECK (capability_digest ~ '^[0-9a-f]{64}$'),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, field_id, season_id, machine_id, capability_digest),
    UNIQUE (capability_id, tenant_id),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (well_id, tenant_id) REFERENCES irrigation_wells(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (pump_id, tenant_id) REFERENCES irrigation_pumps(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (controller_id, tenant_id) REFERENCES irrigation_controllers(id, tenant_id) ON DELETE RESTRICT,
    FOREIGN KEY (energy_system_id, tenant_id) REFERENCES irrigation_energy_systems(id, tenant_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS irrigation_capability_graph_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    capability_id TEXT NOT NULL,
    node_type TEXT NOT NULL CHECK (node_type IN ('well','hydraulic','machine','sprinkler','energy','controller')),
    asset_id TEXT,
    state TEXT NOT NULL CHECK (state IN ('available','degraded','blocked','missing')),
    source_capability_digest CHAR(64) CHECK (source_capability_digest IS NULL OR source_capability_digest ~ '^[0-9a-f]{64}$'),
    blocking_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, capability_id, node_type),
    FOREIGN KEY (capability_id, tenant_id) REFERENCES canonical_irrigation_capability_graphs(capability_id, tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irrigation_capability_graph_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    capability_id TEXT NOT NULL,
    source_node_type TEXT NOT NULL CHECK (source_node_type IN ('well','hydraulic','machine','sprinkler','energy','controller')),
    target_node_type TEXT NOT NULL CHECK (target_node_type IN ('well','hydraulic','machine','sprinkler','energy','controller')),
    relationship TEXT NOT NULL CHECK (relationship IN ('supplies','delivers_to','applies_through','powered_by','controlled_by')),
    state TEXT NOT NULL CHECK (state IN ('available','degraded','blocked','missing')),
    limiting_value NUMERIC,
    limiting_unit TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, capability_id, source_node_type, target_node_type, relationship),
    FOREIGN KEY (capability_id, tenant_id) REFERENCES canonical_irrigation_capability_graphs(capability_id, tenant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_irrigation_capability_graph_field_season
    ON canonical_irrigation_capability_graphs (tenant_id, field_id, season_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_irrigation_capability_graph_machine
    ON canonical_irrigation_capability_graphs (tenant_id, machine_id, created_at DESC);

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'canonical_irrigation_capability_graphs',
        'irrigation_capability_graph_nodes',
        'irrigation_capability_graph_edges'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
        EXECUTE format(
            $p$CREATE POLICY tenant_isolation ON %I
               USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
               WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))$p$,
            t
        );
    END LOOP;
END $$;

COMMIT;
