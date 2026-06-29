-- v105 Marketplace + Ecosystem + Developer Platform
-- Idempotent schema additions for Phase 12. These tables are tenant-scoped and
-- deliberately separate runtime contracts from third-party plugin execution.

CREATE TABLE IF NOT EXISTS marketplace_apps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    author TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'agronomy',
    manifest JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'review',
    risk_level TEXT NOT NULL DEFAULT 'medium',
    review_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS marketplace_installations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    app_id UUID NOT NULL REFERENCES marketplace_apps(id) ON DELETE CASCADE,
    granted_permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'active',
    installed_by UUID,
    quota JSONB NOT NULL DEFAULT '{}'::jsonb,
    installed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, app_id)
);

CREATE TABLE IF NOT EXISTS plugin_permission_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    installation_id UUID REFERENCES marketplace_installations(id) ON DELETE SET NULL,
    permission TEXT NOT NULL,
    allowed BOOLEAN NOT NULL,
    reason TEXT,
    elevated_audit BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    url TEXT NOT NULL,
    events JSONB NOT NULL DEFAULT '[]'::jsonb,
    secret_ref TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, url)
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    webhook_id UUID REFERENCES webhook_subscriptions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (webhook_id, event_id)
);

CREATE TABLE IF NOT EXISTS connector_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    connector_type TEXT NOT NULL,
    capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    auth_mode TEXT NOT NULL DEFAULT 'oauth2',
    required_permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
    sync_modes JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'available',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usage_metering_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    app_id UUID,
    meter TEXT NOT NULL,
    quantity NUMERIC NOT NULL CHECK (quantity >= 0),
    idempotency_key TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, app_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_marketplace_apps_status ON marketplace_apps(status);
CREATE INDEX IF NOT EXISTS idx_marketplace_installations_tenant ON marketplace_installations(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_pending ON webhook_deliveries(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_usage_metering_tenant_meter ON usage_metering_records(tenant_id, meter, recorded_at DESC);

ALTER TABLE marketplace_apps ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketplace_installations ENABLE ROW LEVEL SECURITY;
ALTER TABLE plugin_permission_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE connector_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_metering_records ENABLE ROW LEVEL SECURITY;
