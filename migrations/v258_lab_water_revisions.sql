-- v258 — water lab result revisions.
--
-- water_lab_result_sets: a correction is a new row that names the row it replaces
-- (supersedes_result_set_id); the replaced row keeps its approval and publication stamps.
-- request_digest lets a retry of the same measurement return the stored row.
-- (The stored soil-sampling plan copies of the v26 delivery are held back with the chain's
-- task routes; owner decision 2026-11-13: that table belongs to soil-service.)
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
