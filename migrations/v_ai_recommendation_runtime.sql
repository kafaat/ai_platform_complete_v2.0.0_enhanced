
-- AI recommendation runtime persistence.
CREATE TABLE IF NOT EXISTS recommendation_reviews (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    field_id TEXT NOT NULL,
    recommendation_id TEXT NOT NULL,
    state TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    published_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS review_decisions (
    id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL REFERENCES recommendation_reviews(id),
    reviewer_id TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    modifications JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendation_feedback (
    id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    field_id TEXT NOT NULL,
    accepted BOOLEAN,
    actual_yield DOUBLE PRECISION,
    predicted_yield DOUBLE PRECISION,
    actual_cost DOUBLE PRECISION,
    standard_cost DOUBLE PRECISION,
    actual_water DOUBLE PRECISION,
    standard_water DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_reviews_tenant_field ON recommendation_reviews(tenant_id, field_id);
CREATE INDEX IF NOT EXISTS idx_review_decisions_review ON review_decisions(review_id);
CREATE INDEX IF NOT EXISTS idx_recommendation_feedback_tenant_field ON recommendation_feedback(tenant_id, field_id);


-- Tenant isolation for AI recommendation runtime tables.
-- These tables carry tenant_id and must be fail-closed like the rest of the field decision runtime.
DO $$
BEGIN
    IF to_regproc('_sahool_apply_tenant_rls') IS NOT NULL THEN
        PERFORM _sahool_apply_tenant_rls('recommendation_reviews');
        PERFORM _sahool_apply_tenant_rls('recommendation_feedback');
    ELSE
        ALTER TABLE recommendation_reviews ENABLE ROW LEVEL SECURITY;
        ALTER TABLE recommendation_reviews FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation ON recommendation_reviews;
        CREATE POLICY tenant_isolation ON recommendation_reviews
            USING (tenant_id = current_setting('app.current_tenant', true))
            WITH CHECK (tenant_id = current_setting('app.current_tenant', true));

        ALTER TABLE recommendation_feedback ENABLE ROW LEVEL SECURITY;
        ALTER TABLE recommendation_feedback FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation ON recommendation_feedback;
        CREATE POLICY tenant_isolation ON recommendation_feedback
            USING (tenant_id = current_setting('app.current_tenant', true))
            WITH CHECK (tenant_id = current_setting('app.current_tenant', true));
    END IF;
END $$;
