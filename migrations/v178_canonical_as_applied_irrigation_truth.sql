-- M2.11 canonical as-applied irrigation truth.
CREATE TABLE IF NOT EXISTS as_applied_irrigation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    machine_id UUID NOT NULL,
    controller_id UUID NOT NULL,
    decision_id TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    execution_plan_id TEXT NOT NULL,
    plan_digest CHAR(64) NOT NULL,
    planned_depth_mm DOUBLE PRECISION NOT NULL CHECK (planned_depth_mm > 0),
    planned_volume_m3 DOUBLE PRECISION NOT NULL CHECK (planned_volume_m3 > 0),
    planned_area_ha DOUBLE PRECISION NOT NULL CHECK (planned_area_ha > 0),
    irrigation_capability_digest CHAR(64) NOT NULL,
    commissioning_certification_digest CHAR(64) NOT NULL,
    decision_content_digest CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, execution_plan_id),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS as_applied_irrigation_receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    run_id UUID NOT NULL,
    controller_id UUID NOT NULL,
    receipt_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('accepted','running','completed','stopped','failed','cancelled')),
    sequence_number BIGINT NOT NULL CHECK (sequence_number >= 0),
    observed_at TIMESTAMPTZ NOT NULL,
    controller_command_digest CHAR(64) NOT NULL,
    payload_digest CHAR(64) NOT NULL,
    receipt_digest CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, run_id) REFERENCES as_applied_irrigation_runs (tenant_id, id),
    UNIQUE (tenant_id, controller_id, receipt_id),
    UNIQUE (tenant_id, controller_id, sequence_number),
    UNIQUE (tenant_id, receipt_digest)
);

CREATE TABLE IF NOT EXISTS as_applied_irrigation_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    run_id UUID NOT NULL,
    controller_id UUID NOT NULL,
    observation_type TEXT NOT NULL CHECK (observation_type IN ('flow','pressure','runtime','position')),
    sequence_number BIGINT NOT NULL CHECK (sequence_number >= 0),
    observed_at TIMESTAMPTZ NOT NULL,
    value DOUBLE PRECISION NOT NULL CHECK (value >= 0),
    unit TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    payload_digest CHAR(64) NOT NULL,
    observation_digest CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, run_id) REFERENCES as_applied_irrigation_runs (tenant_id, id),
    UNIQUE (tenant_id, controller_id, source_message_id),
    UNIQUE (tenant_id, controller_id, sequence_number),
    UNIQUE (tenant_id, observation_digest)
);

CREATE TABLE IF NOT EXISTS canonical_as_applied_irrigation_truths (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    run_id UUID NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified','blocked')),
    verification_status TEXT NOT NULL CHECK (verification_status IN ('verified','unverified')),
    actual_start_at TIMESTAMPTZ,
    actual_end_at TIMESTAMPTZ,
    actual_runtime_minutes DOUBLE PRECISION,
    actual_volume_m3 DOUBLE PRECISION,
    actual_depth_mm DOUBLE PRECISION,
    actual_area_ha DOUBLE PRECISION,
    mean_flow_lps DOUBLE PRECISION,
    mean_pressure_bar DOUBLE PRECISION,
    position_coverage_percent DOUBLE PRECISION,
    volume_variance_m3 DOUBLE PRECISION,
    volume_variance_percent DOUBLE PRECISION,
    depth_variance_mm DOUBLE PRECISION,
    depth_variance_percent DOUBLE PRECISION,
    completion_ratio DOUBLE PRECISION,
    water_ledger_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    source_lineage JSONB NOT NULL,
    blocking_reasons JSONB NOT NULL,
    limitations JSONB NOT NULL,
    as_applied_digest CHAR(64) NOT NULL,
    snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, run_id) REFERENCES as_applied_irrigation_runs (tenant_id, id),
    UNIQUE (tenant_id, run_id, as_applied_digest),
    UNIQUE (tenant_id, as_applied_digest)
);

CREATE INDEX IF NOT EXISTS ix_as_applied_runs_field_season
    ON as_applied_irrigation_runs (tenant_id, field_id, season_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_as_applied_receipts_run
    ON as_applied_irrigation_receipts (tenant_id, run_id, sequence_number);
CREATE INDEX IF NOT EXISTS ix_as_applied_observations_run
    ON as_applied_irrigation_observations (tenant_id, run_id, observation_type, sequence_number);

ALTER TABLE as_applied_irrigation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE as_applied_irrigation_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE as_applied_irrigation_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE as_applied_irrigation_receipts FORCE ROW LEVEL SECURITY;
ALTER TABLE as_applied_irrigation_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE as_applied_irrigation_observations FORCE ROW LEVEL SECURITY;
ALTER TABLE canonical_as_applied_irrigation_truths ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical_as_applied_irrigation_truths FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS as_applied_runs_tenant_policy ON as_applied_irrigation_runs;

CREATE POLICY as_applied_runs_tenant_policy ON as_applied_irrigation_runs
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
DROP POLICY IF EXISTS as_applied_receipts_tenant_policy ON as_applied_irrigation_receipts;
CREATE POLICY as_applied_receipts_tenant_policy ON as_applied_irrigation_receipts
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
DROP POLICY IF EXISTS as_applied_observations_tenant_policy ON as_applied_irrigation_observations;
CREATE POLICY as_applied_observations_tenant_policy ON as_applied_irrigation_observations
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
DROP POLICY IF EXISTS canonical_as_applied_truths_tenant_policy ON canonical_as_applied_irrigation_truths;
CREATE POLICY canonical_as_applied_truths_tenant_policy ON canonical_as_applied_irrigation_truths
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
