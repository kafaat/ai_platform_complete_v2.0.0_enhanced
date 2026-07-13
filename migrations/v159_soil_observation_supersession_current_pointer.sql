-- v159 — append-only observation supersession + explicit current soil profile pointer.
CREATE TABLE IF NOT EXISTS soil_observation_supersessions (
    tenant_id UUID NOT NULL,
    superseded_observation_id VARCHAR(80) NOT NULL REFERENCES soil_observations(observation_id) ON DELETE RESTRICT,
    replacement_observation_id VARCHAR(80) NOT NULL REFERENCES soil_observations(observation_id) ON DELETE RESTRICT,
    reason VARCHAR(160),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, superseded_observation_id),
    UNIQUE (tenant_id, replacement_observation_id),
    CHECK (superseded_observation_id <> replacement_observation_id)
);

CREATE TABLE IF NOT EXISTS soil_profile_current (
    tenant_id UUID NOT NULL,
    field_id VARCHAR(128) NOT NULL,
    current_profile_id VARCHAR(128) NOT NULL REFERENCES soil_profile_snapshots(profile_id) ON DELETE RESTRICT,
    projected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    projection_reason VARCHAR(80) NOT NULL DEFAULT 'rebuild',
    PRIMARY KEY (tenant_id, field_id)
);

CREATE INDEX IF NOT EXISTS idx_soil_supersession_replacement
  ON soil_observation_supersessions(tenant_id, replacement_observation_id);
CREATE INDEX IF NOT EXISTS idx_soil_profile_current_profile
  ON soil_profile_current(tenant_id, current_profile_id);

ALTER TABLE soil_observation_supersessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_observation_supersessions FORCE ROW LEVEL SECURITY;
ALTER TABLE soil_profile_current ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_profile_current FORCE ROW LEVEL SECURITY;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['soil_observation_supersessions','soil_profile_current'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), '''')) WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))', t
    );
  END LOOP;
END $$;

COMMENT ON TABLE soil_observation_supersessions IS 'Append-only correction links; superseded evidence remains auditable but is excluded from projection. v159.';
COMMENT ON TABLE soil_profile_current IS 'Explicit current projection pointer, updated transactionally after every successful rebuild. v159.';
