-- v112: Mobile/offline sync runtime contracts, stable operation identifiers and status/audit tables.

CREATE TABLE IF NOT EXISTS mobile_sync_clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    app_version TEXT,
    platform TEXT,
    last_cursor TEXT,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, user_id, device_id)
);

CREATE TABLE IF NOT EXISTS mobile_sync_conflicts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    op_id UUID NOT NULL,
    user_id TEXT,
    field_id UUID,
    conflict_kind TEXT NOT NULL DEFAULT 'optimistic_row_version',
    client_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    server_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    UNIQUE (tenant_id, op_id)
);

CREATE INDEX IF NOT EXISTS idx_mobile_sync_clients_tenant_seen
    ON mobile_sync_clients (tenant_id, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_mobile_sync_conflicts_tenant_status
    ON mobile_sync_conflicts (tenant_id, status, created_at DESC);

ALTER TABLE mobile_sync_clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE mobile_sync_conflicts ENABLE ROW LEVEL SECURITY;
ALTER TABLE mobile_sync_clients FORCE ROW LEVEL SECURITY;
ALTER TABLE mobile_sync_conflicts FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS mobile_sync_clients_tenant_isolation ON mobile_sync_clients;
CREATE POLICY mobile_sync_clients_tenant_isolation ON mobile_sync_clients
    USING (tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS mobile_sync_conflicts_tenant_isolation ON mobile_sync_conflicts;
CREATE POLICY mobile_sync_conflicts_tenant_isolation ON mobile_sync_conflicts
    USING (tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
