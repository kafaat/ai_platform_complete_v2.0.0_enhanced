-- v157 — durable soil profile projection jobs + reconciliation checkpoints.
CREATE TABLE IF NOT EXISTS soil_profile_projection_jobs (
    job_id              BIGSERIAL PRIMARY KEY,
    tenant_id           UUID NOT NULL,
    field_id            VARCHAR(128) NOT NULL,
    reason              VARCHAR(64) NOT NULL DEFAULT 'observation_ingested',
    status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','running','retry','completed','dead_letter')),
    attempts            INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_owner         VARCHAR(128),
    lease_expires_at    TIMESTAMPTZ,
    last_error          TEXT,
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_soil_projection_active_field
    ON soil_profile_projection_jobs(tenant_id, field_id)
    WHERE status IN ('pending','running','retry');
CREATE INDEX IF NOT EXISTS idx_soil_projection_jobs_claim
    ON soil_profile_projection_jobs(status, available_at, lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_soil_projection_jobs_field
    ON soil_profile_projection_jobs(tenant_id, field_id, requested_at DESC);

CREATE TABLE IF NOT EXISTS soil_reconciliation_checkpoints (
    source_name         VARCHAR(64) NOT NULL,
    tenant_id           UUID NOT NULL,
    last_source_id      BIGINT NOT NULL DEFAULT 0,
    rows_scanned        BIGINT NOT NULL DEFAULT 0,
    rows_inserted       BIGINT NOT NULL DEFAULT 0,
    last_run_at         TIMESTAMPTZ,
    last_error          TEXT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source_name, tenant_id)
);

ALTER TABLE soil_profile_projection_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_profile_projection_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE soil_reconciliation_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_reconciliation_checkpoints FORCE ROW LEVEL SECURITY;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['soil_profile_projection_jobs','soil_reconciliation_checkpoints'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), '''')) WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))', t
    );
  END LOOP;
END $$;

COMMENT ON TABLE soil_profile_projection_jobs IS 'Durable retryable jobs for SoilProfileSnapshot projection. v157.';
COMMENT ON TABLE soil_reconciliation_checkpoints IS 'Per-tenant historical soil evidence reconciliation cursors. v157.';

-- Cross-tenant worker claim boundary. The function returns only the job identity and tenant,
-- and is executable only by the constrained application role when present.
CREATE OR REPLACE FUNCTION sahool_claim_soil_projection_job(
    p_worker_id text,
    p_lease_seconds integer DEFAULT 120
)
RETURNS TABLE(job_id bigint, tenant_id text, field_id text, attempts integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
  RETURN QUERY
  WITH candidate AS (
      SELECT j.job_id
      FROM soil_profile_projection_jobs j
      WHERE j.status IN ('pending','retry','running')
        AND j.available_at <= NOW()
        AND (j.status <> 'running' OR j.lease_expires_at < NOW())
      ORDER BY j.available_at, j.job_id
      FOR UPDATE SKIP LOCKED
      LIMIT 1
  )
  UPDATE soil_profile_projection_jobs j
  SET status='running', lease_owner=p_worker_id,
      lease_expires_at=NOW()+make_interval(secs => GREATEST(1,p_lease_seconds)),
      attempts=j.attempts+1, updated_at=NOW()
  FROM candidate c
  WHERE j.job_id=c.job_id
  RETURNING j.job_id, j.tenant_id::text, j.field_id::text, j.attempts;
END $$;

CREATE OR REPLACE FUNCTION sahool_finish_soil_projection_job(
    p_job_id bigint,
    p_status text,
    p_retry_seconds integer DEFAULT 0,
    p_error text DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
  IF p_status NOT IN ('completed','retry','dead_letter') THEN
    RAISE EXCEPTION 'invalid soil projection terminal status: %', p_status;
  END IF;
  UPDATE soil_profile_projection_jobs
  SET status=p_status,
      available_at=CASE WHEN p_status='retry'
                        THEN NOW()+make_interval(secs => GREATEST(1,p_retry_seconds))
                        ELSE available_at END,
      completed_at=CASE WHEN p_status='completed' THEN NOW() ELSE completed_at END,
      lease_owner=NULL, lease_expires_at=NULL,
      last_error=LEFT(p_error,4000), updated_at=NOW()
  WHERE job_id=p_job_id;
END $$;

REVOKE ALL ON FUNCTION sahool_claim_soil_projection_job(text,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION sahool_finish_soil_projection_job(bigint,text,integer,text) FROM PUBLIC;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sahool_app') THEN
    GRANT EXECUTE ON FUNCTION sahool_claim_soil_projection_job(text,integer) TO sahool_app;
    GRANT EXECUTE ON FUNCTION sahool_finish_soil_projection_job(bigint,text,integer,text) TO sahool_app;
  END IF;
END $$;
