-- v156 — durable soil/water laboratory workflow and immutable analyte results.
-- Replaces process-local dictionaries in platform lab routes. Tenant-isolated, append-only evidence.

CREATE TABLE IF NOT EXISTS lab_samples (
    sample_id VARCHAR(64) PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL REFERENCES fields(field_id) ON DELETE CASCADE,
    kind VARCHAR(12) NOT NULL CHECK (kind IN ('soil','water')),
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    sampled_on DATE,
    depth_cm_from NUMERIC(8,2),
    depth_cm_to NUMERIC(8,2),
    source VARCHAR(120),
    status VARCHAR(24) NOT NULL DEFAULT 'requested'
      CHECK (status IN ('requested','sampled','in_lab','result_received','approved','published','rejected','cancelled')),
    gps_accuracy_m NUMERIC(10,2),
    sampling_plan_id VARCHAR(64),
    barcode VARCHAR(128),
    collected_by VARCHAR(64),
    created_by VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (depth_cm_from IS NULL OR depth_cm_from >= 0),
    CHECK (depth_cm_to IS NULL OR depth_cm_to > COALESCE(depth_cm_from, -1)),
    CHECK (kind <> 'soil' OR (depth_cm_from IS NOT NULL AND depth_cm_to IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS lab_sample_custody_events (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    sample_id VARCHAR(64) NOT NULL REFERENCES lab_samples(sample_id) ON DELETE CASCADE,
    event_type VARCHAR(32) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    actor_id VARCHAR(64) NOT NULL,
    location TEXT,
    condition_notes TEXT,
    seal_id VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS soil_lab_results (
    result_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    sample_id VARCHAR(64) NOT NULL REFERENCES lab_samples(sample_id) ON DELETE RESTRICT,
    analyte VARCHAR(64) NOT NULL,
    value_json JSONB NOT NULL,
    unit VARCHAR(32),
    method_code VARCHAR(128),
    detection_limit NUMERIC,
    uncertainty NUMERIC,
    quality_status VARCHAR(24) NOT NULL DEFAULT 'unreviewed'
      CHECK (quality_status IN ('unreviewed','approved','rejected','superseded')),
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_by VARCHAR(64),
    approved_at TIMESTAMPTZ,
    supersedes_result_id UUID REFERENCES soil_lab_results(result_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sample_id, analyte, result_id)
);

CREATE TABLE IF NOT EXISTS water_lab_result_sets (
    result_set_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    sample_id VARCHAR(64) NOT NULL REFERENCES lab_samples(sample_id) ON DELETE RESTRICT,
    payload JSONB NOT NULL,
    analysis JSONB NOT NULL,
    quality_status VARCHAR(24) NOT NULL DEFAULT 'unreviewed'
      CHECK (quality_status IN ('unreviewed','approved','rejected','superseded')),
    observed_at TIMESTAMPTZ NOT NULL,
    approved_by VARCHAR(64),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lab_samples_tenant_field ON lab_samples(tenant_id, field_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lab_samples_status ON lab_samples(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_lab_custody_sample ON lab_sample_custody_events(tenant_id, sample_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_soil_lab_results_sample ON soil_lab_results(tenant_id, sample_id, analyte, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_water_lab_results_sample ON water_lab_result_sets(tenant_id, sample_id, observed_at DESC);

ALTER TABLE lab_samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE lab_samples FORCE ROW LEVEL SECURITY;
ALTER TABLE lab_sample_custody_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE lab_sample_custody_events FORCE ROW LEVEL SECURITY;
ALTER TABLE soil_lab_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_lab_results FORCE ROW LEVEL SECURITY;
ALTER TABLE water_lab_result_sets ENABLE ROW LEVEL SECURITY;
ALTER TABLE water_lab_result_sets FORCE ROW LEVEL SECURITY;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['lab_samples','lab_sample_custody_events','soil_lab_results','water_lab_result_sets'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), '''')) WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))', t
    );
  END LOOP;
END $$;

COMMENT ON TABLE lab_samples IS 'Durable governed sample lifecycle. v156.';
COMMENT ON TABLE soil_lab_results IS 'Immutable one-result-per-analyte laboratory evidence. v156.';
