-- Phase 8: Global-scale GIS runtime metadata.
-- Stores release gates, regional topology, SLO budgets and load-test evidence.

CREATE TABLE IF NOT EXISTS global_gis_topology (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    topology_id TEXT NOT NULL,
    home_region TEXT NOT NULL,
    satellite_regions JSONB NOT NULL DEFAULT '[]'::jsonb,
    sharding JSONB NOT NULL DEFAULT '{}'::jsonb,
    traffic_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_global_gis_topology_tenant_created
    ON global_gis_topology (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS global_gis_release_gate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    gate_version TEXT NOT NULL DEFAULT 'phase8',
    ready BOOLEAN NOT NULL DEFAULT false,
    blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_global_gis_release_gate_tenant_eval
    ON global_gis_release_gate (tenant_id, evaluated_at DESC);

ALTER TABLE global_gis_topology ENABLE ROW LEVEL SECURITY;
ALTER TABLE global_gis_topology FORCE ROW LEVEL SECURITY;
ALTER TABLE global_gis_release_gate ENABLE ROW LEVEL SECURITY;
ALTER TABLE global_gis_release_gate FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS global_gis_topology_tenant_isolation ON global_gis_topology;
CREATE POLICY global_gis_topology_tenant_isolation ON global_gis_topology
    USING (tenant_id::text = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS global_gis_release_gate_tenant_isolation ON global_gis_release_gate;
CREATE POLICY global_gis_release_gate_tenant_isolation ON global_gis_release_gate
    USING (tenant_id::text = current_setting('app.tenant_id', true));
