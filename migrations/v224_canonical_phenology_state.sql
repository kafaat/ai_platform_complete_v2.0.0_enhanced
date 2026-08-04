-- v224: canonical, append-only crop phenology observations and reconciled states.
CREATE TABLE IF NOT EXISTS phenology_observations (
    tenant_id uuid NOT NULL,
    observation_id text NOT NULL,
    field_id text NOT NULL,
    season_id text NOT NULL,
    crop_id text NOT NULL,
    cultivar_id text,
    source text NOT NULL CHECK (source IN ('field_scout','agronomist','farmer','sensor')),
    stage text NOT NULL,
    observed_at timestamptz NOT NULL,
    confidence double precision NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence_digest text NOT NULL CHECK (evidence_digest ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, observation_id)
);

CREATE TABLE IF NOT EXISTS canonical_phenology_states (
    tenant_id uuid NOT NULL,
    state_digest text NOT NULL CHECK (state_digest ~ '^[0-9a-f]{64}$'),
    field_id text NOT NULL,
    season_id text NOT NULL,
    crop_id text NOT NULL,
    cultivar_id text,
    as_of timestamptz NOT NULL,
    sowing_date date NOT NULL,
    days_since_sowing integer NOT NULL CHECK (days_since_sowing >= 0),
    observed_stage text,
    predicted_stage text,
    canonical_stage text,
    status text NOT NULL CHECK (status IN ('observed','predicted','blocked')),
    confidence double precision CHECK (confidence >= 0 AND confidence <= 1),
    accumulated_gdd double precision CHECK (accumulated_gdd >= 0),
    gdd_fraction double precision CHECK (gdd_fraction >= 0),
    stage_divergence text NOT NULL,
    observation_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_digests jsonb NOT NULL DEFAULT '[]'::jsonb,
    limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, state_digest),
    UNIQUE (tenant_id, field_id, season_id, as_of)
);

ALTER TABLE phenology_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE phenology_observations FORCE ROW LEVEL SECURITY;
ALTER TABLE canonical_phenology_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical_phenology_states FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON phenology_observations;
CREATE POLICY tenant_isolation ON phenology_observations
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

DROP POLICY IF EXISTS tenant_isolation ON canonical_phenology_states;
CREATE POLICY tenant_isolation ON canonical_phenology_states
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE OR REPLACE FUNCTION reject_phenology_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'phenology evidence is append-only'; END $$;

DROP TRIGGER IF EXISTS phenology_observations_append_only ON phenology_observations;
CREATE TRIGGER phenology_observations_append_only
BEFORE UPDATE OR DELETE ON phenology_observations
FOR EACH ROW EXECUTE FUNCTION reject_phenology_mutation();

DROP TRIGGER IF EXISTS canonical_phenology_states_append_only ON canonical_phenology_states;
CREATE TRIGGER canonical_phenology_states_append_only
BEFORE UPDATE OR DELETE ON canonical_phenology_states
FOR EACH ROW EXECUTE FUNCTION reject_phenology_mutation();
