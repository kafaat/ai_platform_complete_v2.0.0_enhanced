-- v155 — canonical soil evidence store + immutable SoilProfileSnapshot projection.
CREATE TABLE IF NOT EXISTS soil_observations (
    observation_id      VARCHAR(80) PRIMARY KEY,
    contract_version    VARCHAR(40) NOT NULL CHECK (contract_version = 'soil-observation.v1'),
    tenant_id           UUID NOT NULL,
    field_id            VARCHAR(128) NOT NULL,
    zone_id             VARCHAR(128),
    property             VARCHAR(96) NOT NULL,
    value_json           JSONB NOT NULL,
    unit                 VARCHAR(48),
    depth_from_cm        NUMERIC(8,2) NOT NULL CHECK (depth_from_cm >= 0),
    depth_to_cm          NUMERIC(8,2) NOT NULL CHECK (depth_to_cm > depth_from_cm),
    observed_at          TIMESTAMPTZ NOT NULL,
    received_at          TIMESTAMPTZ NOT NULL,
    source_type          VARCHAR(32) NOT NULL,
    source_id            VARCHAR(160),
    procedure_id         VARCHAR(160),
    calibration_id       VARCHAR(160),
    quality_status       VARCHAR(32) NOT NULL,
    quality_flags        JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence           NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    idempotency_key      VARCHAR(256) NOT NULL,
    provenance           JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_soil_observation_field_property_time
    ON soil_observations(tenant_id, field_id, property, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_soil_observation_source
    ON soil_observations(tenant_id, source_type, source_id);

CREATE TABLE IF NOT EXISTS soil_profile_snapshots (
    profile_id           VARCHAR(128) PRIMARY KEY,
    profile_hash         CHAR(64) NOT NULL UNIQUE,
    contract_version     VARCHAR(40) NOT NULL CHECK (contract_version = 'soil-profile.v1'),
    tenant_id            UUID NOT NULL,
    field_id             VARCHAR(128) NOT NULL,
    zone_id              VARCHAR(128),
    effective_at         TIMESTAMPTZ NOT NULL,
    data_available_at    TIMESTAMPTZ NOT NULL,
    status               VARCHAR(40) NOT NULL,
    evidence_level       VARCHAR(40) NOT NULL,
    completeness_score   NUMERIC(5,4) NOT NULL CHECK (completeness_score >= 0 AND completeness_score <= 1),
    quality_passed       BOOLEAN NOT NULL,
    executable           BOOLEAN NOT NULL DEFAULT FALSE,
    selection_policy_version VARCHAR(80) NOT NULL,
    snapshot             JSONB NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_soil_profile_current
    ON soil_profile_snapshots(tenant_id, field_id, zone_id, effective_at DESC);

SELECT _sahool_apply_tenant_rls('soil_observations');
SELECT _sahool_apply_tenant_rls('soil_profile_snapshots');
-- Explicit tenant RLS (enable + force + policy) so the canonical soil evidence tables carry
-- their own isolation regardless of the propagate helper — mirrors v156's lab tables.
ALTER TABLE soil_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_observations FORCE ROW LEVEL SECURITY;
ALTER TABLE soil_profile_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_profile_snapshots FORCE ROW LEVEL SECURITY;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['soil_observations','soil_profile_snapshots'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), '''')) WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))', t
    );
  END LOOP;
END $$;

COMMENT ON TABLE soil_observations IS 'Canonical append-only soil evidence. v155.';
COMMENT ON TABLE soil_profile_snapshots IS 'Immutable governed SoilProfileSnapshot projections. v155.';
