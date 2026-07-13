-- v166 — immutable runtime certification runs and evidence ledger.
CREATE TABLE IF NOT EXISTS soil_runtime_certification_runs (
    run_id VARCHAR(96) PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id VARCHAR(128) NOT NULL DEFAULT 'release',
    release_ref VARCHAR(160) NOT NULL,
    environment VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('draft','running','blocked','ready_for_approval','certified','revoked')),
    manifest_sha256 CHAR(64),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_soil_runtime_cert_release
  ON soil_runtime_certification_runs(tenant_id,release_ref,environment)
  WHERE status='certified';

CREATE TABLE IF NOT EXISTS soil_runtime_certification_evidence (
    evidence_id VARCHAR(96) PRIMARY KEY,
    tenant_id UUID NOT NULL,
    run_id VARCHAR(96) NOT NULL REFERENCES soil_runtime_certification_runs(run_id) ON DELETE RESTRICT,
    check_name VARCHAR(96) NOT NULL,
    sha256 CHAR(64) NOT NULL,
    uri TEXT,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id,run_id,check_name,sha256)
);

ALTER TABLE soil_runtime_certification_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_runtime_certification_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE soil_runtime_certification_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_runtime_certification_evidence FORCE ROW LEVEL SECURITY;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['soil_runtime_certification_runs','soil_runtime_certification_evidence'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I',t);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant'',true),'''')) WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'',true),''''))',t);
  END LOOP;
END $$;
COMMENT ON TABLE soil_runtime_certification_runs IS 'Fail-closed P6 production certification manifests. v166.';
COMMENT ON TABLE soil_runtime_certification_evidence IS 'Content-addressed evidence ledger for P6 certification checks. v166.';
