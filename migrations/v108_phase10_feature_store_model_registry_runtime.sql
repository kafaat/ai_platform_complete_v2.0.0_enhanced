-- v108: Phase 10 production Feature Store + Model Registry runtime.
-- Additive, RLS-protected tables for feature definitions/versions, immutable
-- dataset versions, model artifacts, serving aliases and rollback history.

CREATE TABLE IF NOT EXISTS feature_definitions_runtime (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    feature_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    value_type TEXT NOT NULL DEFAULT 'unknown',
    owner TEXT NOT NULL DEFAULT 'phase10',
    ttl_hours INTEGER NOT NULL DEFAULT 24,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    transformations JSONB NOT NULL DEFAULT '[]'::jsonb,
    quality_gates JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, feature_id),
    UNIQUE (tenant_id, name, version, entity_type)
);

CREATE TABLE IF NOT EXISTS feature_set_versions_runtime (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    feature_set_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    feature_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    feature_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    registry_version TEXT NOT NULL DEFAULT 'feature-store.v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, feature_set_id)
);

CREATE TABLE IF NOT EXISTS offline_dataset_versions_runtime (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    dataset_version_id TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    version TEXT NOT NULL,
    feature_set_id TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    entity_count INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL,
    object_uri TEXT,
    point_in_time_safe BOOLEAN NOT NULL DEFAULT false,
    missing_event_time_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, dataset_version_id)
);

CREATE TABLE IF NOT EXISTS point_in_time_snapshots_runtime (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    snapshot_id TEXT NOT NULL,
    feature_set_id TEXT,
    as_of TIMESTAMPTZ NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    excluded_count INTEGER NOT NULL DEFAULT 0,
    rows JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, snapshot_id)
);

CREATE TABLE IF NOT EXISTS model_versions_runtime (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    model_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    task TEXT NOT NULL,
    framework TEXT NOT NULL DEFAULT 'python',
    artifact_uri TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    dataset_version_id TEXT,
    feature_set_id TEXT,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'registered',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, model_id),
    UNIQUE (tenant_id, model_name, version, task)
);

CREATE TABLE IF NOT EXISTS model_serving_aliases_runtime (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    alias TEXT NOT NULL,
    model_id TEXT NOT NULL,
    previous_model_id TEXT,
    promotion_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, alias)
);

CREATE TABLE IF NOT EXISTS model_promotion_history_runtime (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    promotion_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    decision TEXT NOT NULL,
    target_model_id TEXT,
    previous_model_id TEXT,
    challenger_model_id TEXT,
    metric_delta JSONB NOT NULL DEFAULT '{}'::jsonb,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    rollback_target_model_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, promotion_id)
);

CREATE TABLE IF NOT EXISTS model_rollback_history_runtime (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    rollback_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    from_model_id TEXT NOT NULL,
    to_model_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, rollback_id)
);

CREATE INDEX IF NOT EXISTS idx_feature_definitions_runtime_lookup ON feature_definitions_runtime(tenant_id, entity_type, name, version);
CREATE INDEX IF NOT EXISTS idx_offline_dataset_versions_runtime_feature_set ON offline_dataset_versions_runtime(tenant_id, feature_set_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_versions_runtime_task ON model_versions_runtime(tenant_id, task, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_serving_aliases_runtime_alias ON model_serving_aliases_runtime(tenant_id, alias);

ALTER TABLE feature_definitions_runtime ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_set_versions_runtime ENABLE ROW LEVEL SECURITY;
ALTER TABLE offline_dataset_versions_runtime ENABLE ROW LEVEL SECURITY;
ALTER TABLE point_in_time_snapshots_runtime ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_versions_runtime ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_serving_aliases_runtime ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_promotion_history_runtime ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_rollback_history_runtime ENABLE ROW LEVEL SECURITY;

ALTER TABLE feature_definitions_runtime FORCE ROW LEVEL SECURITY;
ALTER TABLE feature_set_versions_runtime FORCE ROW LEVEL SECURITY;
ALTER TABLE offline_dataset_versions_runtime FORCE ROW LEVEL SECURITY;
ALTER TABLE point_in_time_snapshots_runtime FORCE ROW LEVEL SECURITY;
ALTER TABLE model_versions_runtime FORCE ROW LEVEL SECURITY;
ALTER TABLE model_serving_aliases_runtime FORCE ROW LEVEL SECURITY;
ALTER TABLE model_promotion_history_runtime FORCE ROW LEVEL SECURITY;
ALTER TABLE model_rollback_history_runtime FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY feature_definitions_runtime_tenant_policy ON feature_definitions_runtime
        USING (tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY feature_set_versions_runtime_tenant_policy ON feature_set_versions_runtime
        USING (tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY offline_dataset_versions_runtime_tenant_policy ON offline_dataset_versions_runtime
        USING (tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY point_in_time_snapshots_runtime_tenant_policy ON point_in_time_snapshots_runtime
        USING (tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY model_versions_runtime_tenant_policy ON model_versions_runtime
        USING (tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY model_serving_aliases_runtime_tenant_policy ON model_serving_aliases_runtime
        USING (tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY model_promotion_history_runtime_tenant_policy ON model_promotion_history_runtime
        USING (tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY model_rollback_history_runtime_tenant_policy ON model_rollback_history_runtime
        USING (tenant_id::text = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
