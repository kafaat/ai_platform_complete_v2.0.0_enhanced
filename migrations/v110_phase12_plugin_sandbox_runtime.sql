-- v110: Phase 12 plugin sandbox/runtime guardrails.
-- Adds auditable plugin execution plans, plugin-originated events, output
-- validation records, and quota ledger entries.  Plugins remain fail-closed:
-- they can propose effects but cannot write DB/NATS/actuators directly.

CREATE TABLE IF NOT EXISTS marketplace_plugin_execution_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    app_id text NOT NULL,
    installation_id text NOT NULL,
    execution_id text NOT NULL UNIQUE,
    action text NOT NULL,
    decision text NOT NULL CHECK (decision IN ('allow','review','deny')),
    required_permission text NOT NULL,
    idempotency_key text NOT NULL,
    payload_digest text NOT NULL,
    sandbox_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
    quota_projection jsonb NOT NULL DEFAULT '{}'::jsonb,
    reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
    audit_level text NOT NULL DEFAULT 'standard',
    status text NOT NULL DEFAULT 'planned',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS marketplace_plugin_runtime_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    app_id text NOT NULL,
    installation_id text NOT NULL,
    execution_id text NOT NULL,
    event_id text NOT NULL UNIQUE,
    event_type text NOT NULL,
    schema_version text NOT NULL DEFAULT '1.0',
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    audit_level text NOT NULL DEFAULT 'standard',
    status text NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS marketplace_plugin_output_validations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    app_id text NOT NULL,
    installation_id text NOT NULL,
    execution_id text NOT NULL,
    valid boolean NOT NULL DEFAULT false,
    findings jsonb NOT NULL DEFAULT '[]'::jsonb,
    allowed_effects jsonb NOT NULL DEFAULT '[]'::jsonb,
    blocked_effects jsonb NOT NULL DEFAULT '[]'::jsonb,
    requires_review boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS marketplace_plugin_quota_ledger (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    app_id text NOT NULL,
    installation_id text NOT NULL,
    execution_id text,
    meter text NOT NULL,
    quantity numeric NOT NULL CHECK (quantity >= 0),
    idempotency_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, app_id, meter, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_marketplace_plugin_execution_tenant_app
    ON marketplace_plugin_execution_runs (tenant_id, app_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_marketplace_plugin_events_tenant_type
    ON marketplace_plugin_runtime_events (tenant_id, event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_marketplace_plugin_quota_tenant_meter
    ON marketplace_plugin_quota_ledger (tenant_id, meter, created_at DESC);

ALTER TABLE marketplace_plugin_execution_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketplace_plugin_execution_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE marketplace_plugin_runtime_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketplace_plugin_runtime_events FORCE ROW LEVEL SECURITY;
ALTER TABLE marketplace_plugin_output_validations ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketplace_plugin_output_validations FORCE ROW LEVEL SECURITY;
ALTER TABLE marketplace_plugin_quota_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketplace_plugin_quota_ledger FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS marketplace_plugin_execution_tenant_isolation ON marketplace_plugin_execution_runs;
CREATE POLICY marketplace_plugin_execution_tenant_isolation ON marketplace_plugin_execution_runs
    USING (tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS marketplace_plugin_events_tenant_isolation ON marketplace_plugin_runtime_events;
CREATE POLICY marketplace_plugin_events_tenant_isolation ON marketplace_plugin_runtime_events
    USING (tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS marketplace_plugin_output_validations_tenant_isolation ON marketplace_plugin_output_validations;
CREATE POLICY marketplace_plugin_output_validations_tenant_isolation ON marketplace_plugin_output_validations
    USING (tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS marketplace_plugin_quota_tenant_isolation ON marketplace_plugin_quota_ledger;
CREATE POLICY marketplace_plugin_quota_tenant_isolation ON marketplace_plugin_quota_ledger
    USING (tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
