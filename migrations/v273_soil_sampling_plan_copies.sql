-- v273: soil-service's stored copies of AI soil-sampling plans (gap P6, sampling plan provenance).
-- Owner and only writer: soil-service (owner decision 2026-11-13; it already owns
-- soil_sampling_plans). The platform never reads this table: its lab-sample route asks
-- soil-service to resolve a plan point, and stores the origin soil-service returns.
-- A copy is immutable once recorded (the plan id is a digest of the plan's points), so a stored
-- plan point cannot be moved after a sample has been taken against it.
-- Re-run safe: IF NOT EXISTS, policy and trigger dropped before they are created.
BEGIN;
SET LOCAL lock_timeout='15s';
CREATE TABLE IF NOT EXISTS soil_sampling_plan_copies (
  tenant_id UUID NOT NULL,
  plan_id VARCHAR(64) NOT NULL CHECK (length(btrim(plan_id)) BETWEEN 1 AND 64),
  field_id VARCHAR(64) NOT NULL CHECK (length(btrim(field_id)) BETWEEN 1 AND 64),
  plan JSONB NOT NULL CHECK (jsonb_typeof(plan) = 'object'),
  sample_points JSONB NOT NULL
    CHECK (jsonb_typeof(sample_points) = 'array' AND jsonb_array_length(sample_points) BETWEEN 1 AND 500),
  plan_digest CHAR(64) NOT NULL CHECK (plan_digest ~ '^[0-9a-f]{64}$'),
  source VARCHAR(64) NOT NULL CHECK (length(btrim(source)) BETWEEN 1 AND 64),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, plan_id)
);
CREATE INDEX IF NOT EXISTS idx_soil_sampling_plan_copies_field
  ON soil_sampling_plan_copies(tenant_id, field_id, recorded_at DESC);
ALTER TABLE soil_sampling_plan_copies ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_sampling_plan_copies FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS soil_sampling_plan_copies_tenant ON soil_sampling_plan_copies;
CREATE POLICY soil_sampling_plan_copies_tenant ON soil_sampling_plan_copies
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
CREATE OR REPLACE FUNCTION soil_sampling_plan_copy_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
  RAISE EXCEPTION 'soil_sampling_plan_copy_immutable' USING ERRCODE = '55000';
END; $$;
DROP TRIGGER IF EXISTS soil_sampling_plan_copies_immutable ON soil_sampling_plan_copies;
CREATE TRIGGER soil_sampling_plan_copies_immutable BEFORE UPDATE ON soil_sampling_plan_copies
  FOR EACH ROW EXECUTE FUNCTION soil_sampling_plan_copy_immutable();
REVOKE ALL ON soil_sampling_plan_copies FROM PUBLIC;
COMMENT ON TABLE soil_sampling_plan_copies IS
  'soil-service copy of each AI soil-sampling plan; lab-sample plan origins are resolved from it. v273.';
COMMIT;
