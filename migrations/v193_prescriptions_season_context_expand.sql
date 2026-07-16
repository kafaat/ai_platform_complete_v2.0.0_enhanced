-- v193: FII Safety Increment 4 — season context expansion for manual prescriptions.
-- Expand only: no guessed backfill and no NOT NULL contract while legacy rows remain unresolved.
ALTER TABLE prescriptions
    ADD COLUMN IF NOT EXISTS season_id TEXT;

ALTER TABLE prescriptions
    ADD COLUMN IF NOT EXISTS season_resolution_status TEXT NOT NULL DEFAULT 'unresolved';

ALTER TABLE prescriptions
    DROP CONSTRAINT IF EXISTS prescriptions_season_resolution_status_check;
ALTER TABLE prescriptions
    ADD CONSTRAINT prescriptions_season_resolution_status_check
    CHECK (season_resolution_status IN ('resolved', 'unresolved', 'not_applicable', 'invalid_legacy'));

CREATE INDEX IF NOT EXISTS idx_prescriptions_tenant_field_season
    ON prescriptions (tenant_id, field_id, season_id, created_at DESC);

COMMENT ON COLUMN prescriptions.season_id IS
    'FII season context. Required for all new writes; legacy rows remain nullable until reliably resolved.';
COMMENT ON COLUMN prescriptions.season_resolution_status IS
    'resolved|unresolved|not_applicable|invalid_legacy. Unresolved legacy prescriptions are frozen from execution.';
