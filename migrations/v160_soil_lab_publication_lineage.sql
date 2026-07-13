-- v160 — laboratory result correction lineage into canonical soil observations.
ALTER TABLE soil_lab_results
  ADD COLUMN IF NOT EXISTS published_observation_id VARCHAR(80),
  ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_soil_lab_results_published_observation
  ON soil_lab_results(tenant_id, published_observation_id)
  WHERE published_observation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_soil_lab_results_supersedes
  ON soil_lab_results(tenant_id, supersedes_result_id)
  WHERE supersedes_result_id IS NOT NULL;

COMMENT ON COLUMN soil_lab_results.published_observation_id IS
  'Canonical soil_observations identity emitted for this analyte result.';
COMMENT ON COLUMN soil_lab_results.supersedes_result_id IS
  'Immutable correction chain to the prior analyte result.';
