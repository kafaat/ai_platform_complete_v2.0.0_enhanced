-- Phase 9: Autonomous Farm OS runtime tables.
-- These tables persist closed-loop execution plans, actuator commands, feature
-- store candidates, model registry entries and experiment assignments.

CREATE TABLE IF NOT EXISTS autonomous_execution_plan (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NULL,
    field_id UUID NOT NULL,
    recommendation_id TEXT NOT NULL,
    source_state_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('shadow','human_approval','supervised_autonomy','full_autonomy')),
    status TEXT NOT NULL,
    safety_gate JSONB NOT NULL DEFAULT '{}'::jsonb,
    verification_plan JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS actuator_command_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NULL,
    field_id UUID NOT NULL,
    execution_plan_id UUID NULL REFERENCES autonomous_execution_plan(id) ON DELETE CASCADE,
    command_id TEXT NOT NULL UNIQUE,
    actuator_type TEXT NOT NULL,
    protocol TEXT NOT NULL,
    target_id TEXT NOT NULL,
    command JSONB NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dispatched_at TIMESTAMPTZ NULL,
    acknowledged_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS execution_verification_event (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NULL,
    field_id UUID NOT NULL,
    execution_id TEXT NOT NULL,
    recommendation_id TEXT NOT NULL,
    status TEXT NOT NULL,
    telemetry JSONB NOT NULL DEFAULT '{}'::jsonb,
    field_response JSONB NOT NULL DEFAULT '{}'::jsonb,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS field_feature_store_candidate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    feature_id TEXT NOT NULL UNIQUE,
    feature_set TEXT NOT NULL,
    source_state_id TEXT NULL,
    event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    features JSONB NOT NULL DEFAULT '{}'::jsonb,
    labels JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS model_registry_version (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    task TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('candidate','champion','archived')),
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    training_feature_sets JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(name, task, version)
);

CREATE TABLE IF NOT EXISTS model_experiment_assignment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id TEXT NOT NULL UNIQUE,
    tenant_id UUID NULL,
    entity_id TEXT NOT NULL,
    experiment_key TEXT NOT NULL,
    variant TEXT NOT NULL,
    bucket INT NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(entity_id, experiment_key)
);

CREATE INDEX IF NOT EXISTS idx_autonomous_execution_field_status ON autonomous_execution_plan(field_id, status);
CREATE INDEX IF NOT EXISTS idx_feature_store_entity_set_time ON field_feature_store_candidate(entity_id, feature_set, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_model_registry_task_status ON model_registry_version(task, status);

-- Runtime Activation Patch: enforce tenant isolation on Phase 9 runtime tables.
ALTER TABLE autonomous_execution_plan ENABLE ROW LEVEL SECURITY;
ALTER TABLE actuator_command_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution_verification_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_feature_store_candidate ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_experiment_assignment ENABLE ROW LEVEL SECURITY;

ALTER TABLE autonomous_execution_plan FORCE ROW LEVEL SECURITY;
ALTER TABLE actuator_command_outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE execution_verification_event FORCE ROW LEVEL SECURITY;
ALTER TABLE field_feature_store_candidate FORCE ROW LEVEL SECURITY;
ALTER TABLE model_experiment_assignment FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY autonomous_execution_plan_tenant_isolation ON autonomous_execution_plan
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY actuator_command_outbox_tenant_isolation ON actuator_command_outbox
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY execution_verification_event_tenant_isolation ON execution_verification_event
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY field_feature_store_candidate_tenant_isolation ON field_feature_store_candidate
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY model_experiment_assignment_tenant_isolation ON model_experiment_assignment
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
