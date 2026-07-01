-- v127 (v49.5 hardening line): Pre-agent evidence and tenant-scope hardening for
-- recommendation_outcomes (retro-hardens the v49 table). Applied after v126.
-- Safe/idempotent migration: adds NOT VALID constraints and replaces the RLS policy
-- with both USING and WITH CHECK. Validation can be run after data cleanup.

ALTER TABLE recommendation_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendation_outcomes FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_reco_outcomes_tenant_not_null'
          AND conrelid = 'recommendation_outcomes'::regclass
    ) THEN
        ALTER TABLE recommendation_outcomes
            ADD CONSTRAINT chk_reco_outcomes_tenant_not_null
            CHECK (tenant_id IS NOT NULL) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_reco_outcomes_predicted_yield_nonnegative'
          AND conrelid = 'recommendation_outcomes'::regclass
    ) THEN
        ALTER TABLE recommendation_outcomes
            ADD CONSTRAINT chk_reco_outcomes_predicted_yield_nonnegative
            CHECK (predicted_yield_t_ha IS NULL OR predicted_yield_t_ha >= 0) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_reco_outcomes_actual_yield_nonnegative'
          AND conrelid = 'recommendation_outcomes'::regclass
    ) THEN
        ALTER TABLE recommendation_outcomes
            ADD CONSTRAINT chk_reco_outcomes_actual_yield_nonnegative
            CHECK (actual_yield_t_ha IS NULL OR actual_yield_t_ha >= 0) NOT VALID;
    END IF;
END $$;

DROP POLICY IF EXISTS tenant_isolation ON recommendation_outcomes;
CREATE POLICY tenant_isolation ON recommendation_outcomes
    USING (
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', TRUE), '')
    )
    WITH CHECK (
        tenant_id IS NOT NULL
        AND tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', TRUE), '')
    );

CREATE INDEX IF NOT EXISTS idx_reco_outcomes_tenant_field_season
    ON recommendation_outcomes (tenant_id, field_id, season_id);
