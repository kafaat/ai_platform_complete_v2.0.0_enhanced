-- Phase 10: Continuous Learning AI + Scientific Simulation foundation
-- Dependency-light schema for feature store manifests, datasets, model lifecycle,
-- online learning events, experiment evaluations, and scenario runs.

CREATE TABLE IF NOT EXISTS feature_set_specs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    feature_set_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    feature_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    label_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    freshness_hours INTEGER NOT NULL DEFAULT 24,
    quality_gates JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, feature_set_id)
);

CREATE TABLE IF NOT EXISTS training_datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    dataset_id TEXT NOT NULL,
    feature_set_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_count INTEGER NOT NULL DEFAULT 0,
    row_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    quality JSONB NOT NULL DEFAULT '{}'::jsonb,
    object_uri TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, dataset_id)
);

CREATE TABLE IF NOT EXISTS model_lifecycle_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    decision_id TEXT NOT NULL,
    task TEXT NOT NULL,
    champion_model_id TEXT,
    challenger_model_id TEXT,
    decision TEXT NOT NULL,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    metric_deltas JSONB NOT NULL DEFAULT '{}'::jsonb,
    rollout JSONB NOT NULL DEFAULT '{}'::jsonb,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, decision_id)
);

CREATE TABLE IF NOT EXISTS online_learning_updates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    update_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    feature_set_id TEXT NOT NULL,
    learning_rate DOUBLE PRECISION NOT NULL DEFAULT 0.01,
    sample_count INTEGER NOT NULL DEFAULT 0,
    label_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    drift_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    action TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, update_id)
);

CREATE TABLE IF NOT EXISTS experiment_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    evaluation_id TEXT NOT NULL,
    experiment_key TEXT NOT NULL,
    variants JSONB NOT NULL DEFAULT '{}'::jsonb,
    winner TEXT,
    decision TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, evaluation_id)
);

CREATE TABLE IF NOT EXISTS scenario_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    scenario_id TEXT NOT NULL,
    field_id UUID,
    crop TEXT,
    assumptions JSONB NOT NULL DEFAULT '{}'::jsonb,
    baseline JSONB NOT NULL DEFAULT '{}'::jsonb,
    projected JSONB NOT NULL DEFAULT '{}'::jsonb,
    deltas JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, scenario_id)
);

ALTER TABLE feature_set_specs ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_lifecycle_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE online_learning_updates ENABLE ROW LEVEL SECURITY;
ALTER TABLE experiment_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE scenario_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE feature_set_specs FORCE ROW LEVEL SECURITY;
ALTER TABLE training_datasets FORCE ROW LEVEL SECURITY;
ALTER TABLE model_lifecycle_decisions FORCE ROW LEVEL SECURITY;
ALTER TABLE online_learning_updates FORCE ROW LEVEL SECURITY;
ALTER TABLE experiment_evaluations FORCE ROW LEVEL SECURITY;
ALTER TABLE scenario_runs FORCE ROW LEVEL SECURITY;

-- Runtime Activation Patch: add explicit tenant policies for Phase 10 tables.
DO $$ BEGIN
    CREATE POLICY feature_set_specs_tenant_isolation ON feature_set_specs
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY training_datasets_tenant_isolation ON training_datasets
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY model_lifecycle_decisions_tenant_isolation ON model_lifecycle_decisions
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY online_learning_updates_tenant_isolation ON online_learning_updates
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY experiment_evaluations_tenant_isolation ON experiment_evaluations
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY scenario_runs_tenant_isolation ON scenario_runs
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
