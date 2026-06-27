-- v107: Phase 9/10 event sourcing, replay, closed-loop verification and drift hardening.
-- Safe additive migration. Tenant scoped, RLS/FORCE protected.

CREATE TABLE IF NOT EXISTS autonomous_event_store (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID,
    field_id UUID,
    event_id TEXT NOT NULL UNIQUE,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    sequence INTEGER,
    schema_version TEXT NOT NULL DEFAULT 'phase9.event.v2',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_autonomous_event_store_tenant_aggregate ON autonomous_event_store(tenant_id, aggregate_type, aggregate_id, sequence, occurred_at);
CREATE INDEX IF NOT EXISTS idx_autonomous_event_store_field_time ON autonomous_event_store(field_id, occurred_at DESC);
ALTER TABLE autonomous_event_store ENABLE ROW LEVEL SECURITY;
ALTER TABLE autonomous_event_store FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS autonomous_event_store_tenant_policy ON autonomous_event_store;
CREATE POLICY autonomous_event_store_tenant_policy ON autonomous_event_store
    USING (tenant_id IS NULL OR tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id IS NULL OR tenant_id::text = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS command_verification_loop (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID,
    field_id UUID,
    execution_id TEXT NOT NULL,
    verification_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    ack_complete BOOLEAN NOT NULL DEFAULT false,
    sensor_ok BOOLEAN NOT NULL DEFAULT false,
    faults JSONB NOT NULL DEFAULT '[]'::jsonb,
    sensor_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    verification JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_command_verification_loop_tenant_execution ON command_verification_loop(tenant_id, execution_id, created_at DESC);
ALTER TABLE command_verification_loop ENABLE ROW LEVEL SECURITY;
ALTER TABLE command_verification_loop FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS command_verification_loop_tenant_policy ON command_verification_loop;
CREATE POLICY command_verification_loop_tenant_policy ON command_verification_loop
    USING (tenant_id IS NULL OR tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id IS NULL OR tenant_id::text = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS learning_drift_reports (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID,
    drift_id TEXT NOT NULL UNIQUE,
    feature_set_id TEXT,
    dataset_id TEXT,
    model_id TEXT,
    overall_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    decision TEXT NOT NULL,
    feature_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    thresholds JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_learning_drift_reports_tenant_decision ON learning_drift_reports(tenant_id, decision, created_at DESC);
ALTER TABLE learning_drift_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning_drift_reports FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS learning_drift_reports_tenant_policy ON learning_drift_reports;
CREATE POLICY learning_drift_reports_tenant_policy ON learning_drift_reports
    USING (tenant_id IS NULL OR tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id IS NULL OR tenant_id::text = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS retraining_jobs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID,
    job_id TEXT NOT NULL UNIQUE,
    model_id TEXT,
    dataset_id TEXT,
    action TEXT NOT NULL,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    drift_score DOUBLE PRECISION,
    reproducibility JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_retraining_jobs_tenant_action ON retraining_jobs(tenant_id, action, created_at DESC);
ALTER TABLE retraining_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE retraining_jobs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS retraining_jobs_tenant_policy ON retraining_jobs;
CREATE POLICY retraining_jobs_tenant_policy ON retraining_jobs
    USING (tenant_id IS NULL OR tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id IS NULL OR tenant_id::text = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS feature_lineage_registry (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID,
    lineage_id TEXT NOT NULL UNIQUE,
    feature_set_id TEXT NOT NULL,
    feature_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    models JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feature_lineage_registry_tenant_feature_set ON feature_lineage_registry(tenant_id, feature_set_id);
ALTER TABLE feature_lineage_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_lineage_registry FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS feature_lineage_registry_tenant_policy ON feature_lineage_registry;
CREATE POLICY feature_lineage_registry_tenant_policy ON feature_lineage_registry
    USING (tenant_id IS NULL OR tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id IS NULL OR tenant_id::text = current_setting('app.tenant_id', true));
