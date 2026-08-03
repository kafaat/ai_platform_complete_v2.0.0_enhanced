-- v225: canonical salinity evidence and reconciled soil/water/crop/drainage state.
CREATE TABLE IF NOT EXISTS salinity_evidence_observations (
    tenant_id uuid NOT NULL,
    evidence_id text NOT NULL,
    field_id text NOT NULL,
    season_id text NOT NULL,
    evidence_type text NOT NULL CHECK (evidence_type IN ('soil_ece','water_quality','drainage','crop_tolerance')),
    observed_at timestamptz NOT NULL,
    evidence_digest text NOT NULL CHECK (evidence_digest ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, evidence_id),
    UNIQUE (tenant_id, evidence_digest)
);

CREATE TABLE IF NOT EXISTS canonical_salinity_states (
    tenant_id uuid NOT NULL,
    state_digest text NOT NULL CHECK (state_digest ~ '^[0-9a-f]{64}$'),
    field_id text NOT NULL,
    season_id text NOT NULL,
    crop_id text NOT NULL,
    cultivar_id text,
    phenology_stage text NOT NULL,
    as_of timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('managed','managed_with_limitations','high_risk','blocked')),
    soil_class text,
    water_risk text,
    sodium_hazard_class text,
    rsc_hazard_class text,
    effective_crop_threshold_ece_dsm double precision CHECK (effective_crop_threshold_ece_dsm > 0),
    estimated_relative_yield double precision CHECK (estimated_relative_yield >= 0 AND estimated_relative_yield <= 1),
    leaching_fraction double precision CHECK (leaching_fraction >= 0 AND leaching_fraction <= 1),
    leaching_feasible boolean,
    drainage_class text NOT NULL CHECK (drainage_class IN ('good','moderate','poor','unknown')),
    operational_recommendation_allowed boolean NOT NULL,
    limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_digests jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, state_digest),
    UNIQUE (tenant_id, field_id, season_id, as_of),
    CHECK (NOT operational_recommendation_allowed OR (leaching_feasible IS TRUE AND drainage_class IN ('good','moderate')))
);

ALTER TABLE salinity_evidence_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE salinity_evidence_observations FORCE ROW LEVEL SECURITY;
ALTER TABLE canonical_salinity_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical_salinity_states FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON salinity_evidence_observations;
CREATE POLICY tenant_isolation ON salinity_evidence_observations
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

DROP POLICY IF EXISTS tenant_isolation ON canonical_salinity_states;
CREATE POLICY tenant_isolation ON canonical_salinity_states
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE OR REPLACE FUNCTION reject_salinity_state_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'salinity evidence is append-only'; END $$;

DROP TRIGGER IF EXISTS salinity_evidence_append_only ON salinity_evidence_observations;
CREATE TRIGGER salinity_evidence_append_only BEFORE UPDATE OR DELETE ON salinity_evidence_observations
FOR EACH ROW EXECUTE FUNCTION reject_salinity_state_mutation();

DROP TRIGGER IF EXISTS canonical_salinity_states_append_only ON canonical_salinity_states;
CREATE TRIGGER canonical_salinity_states_append_only BEFORE UPDATE OR DELETE ON canonical_salinity_states
FOR EACH ROW EXECUTE FUNCTION reject_salinity_state_mutation();
