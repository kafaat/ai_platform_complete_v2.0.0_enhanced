ALTER TABLE irrigation_closed_loop_records ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;
-- v227: event-driven season outcome learning and governed promotion candidates.
CREATE TABLE IF NOT EXISTS decision_learning_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL,
  season_id TEXT NOT NULL, field_id TEXT NOT NULL, event_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('blocked','evaluated','review_ready')),
  outcome_count INTEGER NOT NULL DEFAULT 0, source_digests JSONB NOT NULL,
  evaluation JSONB NOT NULL, learning_digest CHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id,event_id), UNIQUE (tenant_id,learning_digest)
);
CREATE TABLE IF NOT EXISTS governed_model_promotion_candidates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL,
  candidate_id TEXT NOT NULL, season_id TEXT NOT NULL, task TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('blocked','monitor','review_ready','approved','rejected')),
  review_required BOOLEAN NOT NULL DEFAULT TRUE CHECK (review_required),
  auto_promote BOOLEAN NOT NULL DEFAULT FALSE CHECK (NOT auto_promote),
  evidence JSONB NOT NULL, candidate_digest CHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), reviewed_by TEXT, reviewed_at TIMESTAMPTZ,
  UNIQUE (tenant_id,candidate_id), UNIQUE (tenant_id,candidate_digest)
);
DO $$ DECLARE t TEXT; BEGIN
  FOREACH t IN ARRAY ARRAY['decision_learning_runs','governed_model_promotion_candidates'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t||'_tenant_policy', t);
    EXECUTE format('CREATE POLICY %I ON %I USING (tenant_id=current_setting(''app.current_tenant'',true)::uuid) WITH CHECK (tenant_id=current_setting(''app.current_tenant'',true)::uuid)', t||'_tenant_policy', t);
  END LOOP;
END $$;

-- Persisted identifiers-only projection queue consumed by the registered worker.
CREATE TABLE IF NOT EXISTS canonical_projection_requests (
  request_id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  projection_type TEXT NOT NULL CHECK (projection_type IN ('phenology','salinity','nutrient')),
  field_id TEXT NOT NULL,
  season_id TEXT NOT NULL,
  canonical_payload JSONB NOT NULL,
  evidence_payload JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processed','failed')),
  result_event_id UUID,
  error_code TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ,
  UNIQUE (tenant_id, projection_type, request_id)
);
ALTER TABLE canonical_projection_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical_projection_requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS canonical_projection_requests_tenant_policy ON canonical_projection_requests;
CREATE POLICY canonical_projection_requests_tenant_policy ON canonical_projection_requests
  USING (tenant_id=current_setting('app.current_tenant',true)::uuid)
  WITH CHECK (tenant_id=current_setting('app.current_tenant',true)::uuid);
