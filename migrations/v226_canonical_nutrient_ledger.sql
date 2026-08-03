-- v226: Canonical nutrient ledger (SOIL-004)
-- Immutable laboratory/application evidence and reconciled N/P/K balances.

CREATE TABLE IF NOT EXISTS nutrient_evidence_observations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    field_id text NOT NULL,
    season_id text NOT NULL,
    evidence_type text NOT NULL CHECK (evidence_type IN ('soil_lab','crop_demand','as_applied')),
    observed_at timestamptz NOT NULL,
    evidence_digest text NOT NULL CHECK (evidence_digest ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, evidence_digest)
);

CREATE TABLE IF NOT EXISTS canonical_nutrient_ledgers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    field_id text NOT NULL,
    season_id text NOT NULL,
    crop_id text NOT NULL,
    cultivar_id text,
    phenology_stage text NOT NULL CHECK (phenology_stage IN ('initial','development','mid','late','unknown')),
    as_of timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('managed','managed_with_limitations','blocked')),
    operational_recommendation_allowed boolean NOT NULL DEFAULT false,
    balances jsonb NOT NULL,
    total_verified_cost numeric,
    currency text,
    verified_operation_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_digests jsonb NOT NULL DEFAULT '[]'::jsonb,
    ledger_digest text NOT NULL CHECK (ledger_digest ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, field_id, season_id, ledger_digest),
    CHECK (total_verified_cost IS NULL OR total_verified_cost >= 0),
    CHECK (total_verified_cost IS NULL OR currency IS NOT NULL),
    CHECK (NOT operational_recommendation_allowed OR phenology_stage <> 'unknown')
);

ALTER TABLE nutrient_evidence_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE nutrient_evidence_observations FORCE ROW LEVEL SECURITY;
ALTER TABLE canonical_nutrient_ledgers ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical_nutrient_ledgers FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS nutrient_evidence_tenant_isolation ON nutrient_evidence_observations;
CREATE POLICY nutrient_evidence_tenant_isolation ON nutrient_evidence_observations
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

DROP POLICY IF EXISTS canonical_nutrient_ledgers_tenant_isolation ON canonical_nutrient_ledgers;
CREATE POLICY canonical_nutrient_ledgers_tenant_isolation ON canonical_nutrient_ledgers
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE OR REPLACE FUNCTION reject_nutrient_ledger_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'canonical nutrient evidence is append-only';
END;
$$;

DROP TRIGGER IF EXISTS nutrient_evidence_append_only ON nutrient_evidence_observations;
CREATE TRIGGER nutrient_evidence_append_only BEFORE UPDATE OR DELETE ON nutrient_evidence_observations
FOR EACH ROW EXECUTE FUNCTION reject_nutrient_ledger_mutation();

DROP TRIGGER IF EXISTS canonical_nutrient_ledgers_append_only ON canonical_nutrient_ledgers;
CREATE TRIGGER canonical_nutrient_ledgers_append_only BEFORE UPDATE OR DELETE ON canonical_nutrient_ledgers
FOR EACH ROW EXECUTE FUNCTION reject_nutrient_ledger_mutation();
