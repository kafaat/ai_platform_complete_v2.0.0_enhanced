-- v196: IRR-F01 target binding — version-pinned field/management-zone → terminal
-- hydraulic node. Field/zone geometry remains owned by the field/zone domains;
-- this is a read-only binding to an existing v171 terminal node, so the hydraulic
-- path query (source → terminal) can start from a real node without duplicating
-- any geometry SoR. No graph-version reference (topology versioning is deferred).
BEGIN;

CREATE TABLE IF NOT EXISTS irrigation_target_bindings (
    binding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    terminal_node_id UUID NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('field', 'management_zone')),
    target_id TEXT NOT NULL,
    target_version_id TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,
    source_event_id UUID,
    source_aggregate_version INTEGER CHECK (source_aggregate_version IS NULL OR source_aggregate_version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (binding_id, tenant_id),
    FOREIGN KEY (project_id, tenant_id)
        REFERENCES irrigation_projects(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (terminal_node_id, tenant_id)
        REFERENCES irrigation_hydraulic_nodes(id, tenant_id) ON DELETE RESTRICT,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

-- At most one current (open) binding per target.
CREATE UNIQUE INDEX IF NOT EXISTS uq_irrigation_target_binding_current
    ON irrigation_target_bindings (tenant_id, target_type, target_id)
    WHERE valid_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_irrigation_target_binding_node
    ON irrigation_target_bindings (tenant_id, terminal_node_id)
    WHERE valid_to IS NULL;

-- Fail-closed tenant RLS (same posture as v192/v194/v195).
DO $$
BEGIN
    ALTER TABLE irrigation_target_bindings ENABLE ROW LEVEL SECURITY;
    ALTER TABLE irrigation_target_bindings FORCE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation ON irrigation_target_bindings;
    CREATE POLICY tenant_isolation ON irrigation_target_bindings
        USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
        WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''));
END $$;

COMMENT ON TABLE irrigation_target_bindings IS
    'IRR-F01: version-pinned field/management-zone binding to an existing v171 terminal hydraulic node; read-only projection, no geometry SoR duplication.';

COMMIT;
