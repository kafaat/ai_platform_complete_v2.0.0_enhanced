-- v258 — water lab result revisions and stored soil-sampling plan copies.
--
-- water_lab_result_sets: a correction is a new row that names the row it replaces
-- (supersedes_result_set_id); the replaced row keeps its approval and publication stamps.
-- request_digest lets a retry of the same measurement return the stored row.
-- soil_sampling_plan_copies: the plan the AI planner produced, recorded by the platform from
-- the service-authenticated advice event, so a sample's plan point is resolved server side.
ALTER TABLE water_lab_result_sets
  ADD COLUMN IF NOT EXISTS supersedes_result_set_id UUID REFERENCES water_lab_result_sets(result_set_id),
  ADD COLUMN IF NOT EXISTS request_digest TEXT,
  ADD COLUMN IF NOT EXISTS correction_reason TEXT,
  ADD COLUMN IF NOT EXISTS entered_by VARCHAR(64),
  ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

-- One live revision per parent: a rejected revision frees its parent for another attempt.
CREATE UNIQUE INDEX IF NOT EXISTS uq_water_lab_live_revision
  ON water_lab_result_sets(supersedes_result_set_id)
  WHERE supersedes_result_set_id IS NOT NULL AND quality_status <> 'rejected';

CREATE TABLE IF NOT EXISTS soil_sampling_plan_copies (
    tenant_id UUID NOT NULL,
    plan_id VARCHAR(64) NOT NULL,
    field_id VARCHAR(50) NOT NULL REFERENCES fields(field_id) ON DELETE CASCADE,
    plan JSONB NOT NULL,
    sample_points JSONB NOT NULL,
    source VARCHAR(64) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, plan_id)
);
ALTER TABLE soil_sampling_plan_copies ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_sampling_plan_copies FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON soil_sampling_plan_copies;
CREATE POLICY tenant_isolation ON soil_sampling_plan_copies
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
COMMENT ON TABLE soil_sampling_plan_copies IS 'Server-held copy of each AI soil-sampling plan. v258.';
