-- M5 governed irrigation closed-loop learning and production certification.
CREATE TABLE IF NOT EXISTS irrigation_outcome_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    execution_plan_id TEXT NOT NULL,
    measured_at TIMESTAMPTZ NOT NULL,
    outcome_status TEXT NOT NULL CHECK (outcome_status IN ('verified','degraded','blocked')),
    source_digests JSONB NOT NULL,
    payload JSONB NOT NULL,
    outcome_evidence_digest CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, outcome_evidence_digest)
);

CREATE TABLE IF NOT EXISTS irrigation_closed_loop_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    execution_plan_id TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN ('verified','blocked')),
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    water_ledger_reconciled BOOLEAN NOT NULL DEFAULT FALSE,
    outcome_verified BOOLEAN NOT NULL DEFAULT FALSE,
    learning_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    source_lineage JSONB NOT NULL,
    blocking_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    closed_loop_digest CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, execution_plan_id),
    UNIQUE (tenant_id, closed_loop_digest)
);

CREATE TABLE IF NOT EXISTS irrigation_learning_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('blocked','monitor','review_ready','approved','rejected')),
    review_required BOOLEAN NOT NULL DEFAULT TRUE CHECK (review_required = TRUE),
    auto_adjust BOOLEAN NOT NULL DEFAULT FALSE CHECK (auto_adjust = FALSE),
    proposed_parameter_changes JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_lineage JSONB NOT NULL,
    evidence_digest CHAR(64) NOT NULL,
    proposal_digest CHAR(64) NOT NULL,
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, proposal_id),
    UNIQUE (tenant_id, proposal_digest)
);

CREATE TABLE IF NOT EXISTS irrigation_production_certifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    environment TEXT NOT NULL CHECK (environment = 'production'),
    release_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('blocked','certified','revoked','superseded')),
    production_certified BOOLEAN NOT NULL DEFAULT FALSE,
    gate_results JSONB NOT NULL,
    blocking_gates JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_pack_digest CHAR(64),
    certified_by TEXT,
    certified_at TIMESTAMPTZ,
    certification_digest CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (production_certified = FALSE OR (status = 'certified' AND certified_by IS NOT NULL AND certified_at IS NOT NULL AND evidence_pack_digest IS NOT NULL)),
    UNIQUE (tenant_id, release_id),
    UNIQUE (tenant_id, certification_digest)
);

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'irrigation_outcome_evidence',
    'irrigation_closed_loop_records',
    'irrigation_learning_proposals',
    'irrigation_production_certifications'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (tenant_id = current_setting(''app.current_tenant_id'', true)::uuid) WITH CHECK (tenant_id = current_setting(''app.current_tenant_id'', true)::uuid)',
      t || '_tenant_policy', t
    );
  END LOOP;
END $$;
