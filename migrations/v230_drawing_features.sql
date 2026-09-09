-- Drawing persistence belongs to the migration role, never the runtime role.
-- apply_in_compose.sh grants the configured APP_DB_ROLE DML after the manifest;
-- that role intentionally has no CREATE privilege on public.
BEGIN;

CREATE TABLE IF NOT EXISTS drawing_features (
    feature_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id TEXT NULL,
    season_id TEXT NULL,
    kind TEXT NOT NULL,
    workflow TEXT NULL,
    geometry JSONB NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    measurements JSONB NULL,
    validation JSONB NULL,
    draft BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1,
    saved_by TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL
);

-- Adopt legacy tables created by the application as well as fresh tables.
-- CURRENT_USER is the configured migration owner; do not hard-code APP_DB_ROLE.
ALTER TABLE drawing_features OWNER TO CURRENT_USER;
REVOKE ALL ON TABLE drawing_features FROM PUBLIC;

CREATE INDEX IF NOT EXISTS idx_drawing_features_tenant_field
    ON drawing_features(tenant_id, field_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_drawing_features_tenant_kind
    ON drawing_features(tenant_id, kind) WHERE deleted_at IS NULL;

ALTER TABLE drawing_features ENABLE ROW LEVEL SECURITY;
ALTER TABLE drawing_features FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON drawing_features;
CREATE POLICY tenant_isolation ON drawing_features
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

COMMIT;
