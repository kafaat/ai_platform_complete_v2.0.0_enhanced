-- IRR-X1.1: vendor-neutral digital commissioning runtime and execution gate.
CREATE TABLE IF NOT EXISTS irrigation_commissioning_tests_v2 (
    test_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    season_id TEXT,
    system_id TEXT NOT NULL,
    machine_id TEXT,
    pump_id TEXT,
    controller_id TEXT,
    test_type TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('pass','degraded','fail')),
    tested_at TIMESTAMPTZ NOT NULL,
    measured JSONB NOT NULL DEFAULT '{}'::jsonb,
    design JSONB NOT NULL DEFAULT '{}'::jsonb,
    tolerances JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_digests JSONB NOT NULL DEFAULT '[]'::jsonb,
    snapshot JSONB NOT NULL,
    content_digest TEXT NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, system_id, content_digest)
);

CREATE TABLE IF NOT EXISTS irrigation_commissioning_certificates_v2 (
    certificate_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    season_id TEXT,
    system_id TEXT NOT NULL,
    machine_id TEXT,
    pump_id TEXT,
    controller_id TEXT,
    specification_version TEXT NOT NULL,
    specification_digest TEXT NOT NULL CHECK (specification_digest ~ '^[0-9a-f]{64}$'),
    capability_graph_digest TEXT NOT NULL CHECK (capability_graph_digest ~ '^[0-9a-f]{64}$'),
    commissioning_version INTEGER NOT NULL CHECK (commissioning_version > 0),
    status TEXT NOT NULL CHECK (status IN ('draft','testing','pending_review','pass','degraded','fail','expired','revoked','superseded')),
    tested_at TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ NOT NULL,
    flow_curve_digest TEXT,
    pressure_curve_digest TEXT,
    power_curve_digest TEXT,
    safety_interlocks JSONB NOT NULL,
    execution_limits JSONB NOT NULL,
    permitted_execution_modes JSONB NOT NULL,
    blocking_failures JSONB NOT NULL,
    warnings JSONB NOT NULL,
    snapshot JSONB NOT NULL,
    certificate_digest TEXT NOT NULL CHECK (certificate_digest ~ '^[0-9a-f]{64}$'),
    issued_by UUID NOT NULL,
    reviewed_by UUID NOT NULL,
    supersedes_certificate_id TEXT REFERENCES irrigation_commissioning_certificates_v2(certificate_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (valid_until > tested_at),
    CHECK (issued_by <> reviewed_by),
    UNIQUE (tenant_id, system_id, commissioning_version),
    UNIQUE (tenant_id, certificate_digest)
);

CREATE TABLE IF NOT EXISTS irrigation_execution_authorizations_v2 (
    authorization_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    season_id TEXT,
    system_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    requested_mode TEXT NOT NULL CHECK (requested_mode IN ('recommendation_only','manual_estimated','manual_measured','supervised','automated')),
    certificate_id TEXT REFERENCES irrigation_commissioning_certificates_v2(certificate_id),
    certificate_digest TEXT,
    execution_allowed BOOLEAN NOT NULL,
    manual_execution_allowed BOOLEAN NOT NULL,
    blocking_reasons JSONB NOT NULL,
    authorization_digest TEXT NOT NULL CHECK (authorization_digest ~ '^[0-9a-f]{64}$'),
    expires_at TIMESTAMPTZ NOT NULL,
    snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, authorization_digest)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_irrigation_commissioning_one_current
ON irrigation_commissioning_certificates_v2 (tenant_id, system_id)
WHERE status IN ('pass','degraded');

CREATE INDEX IF NOT EXISTS idx_irrigation_commissioning_tests_latest
ON irrigation_commissioning_tests_v2 (tenant_id, system_id, test_type, tested_at DESC);
CREATE INDEX IF NOT EXISTS idx_irrigation_commissioning_cert_validity
ON irrigation_commissioning_certificates_v2 (tenant_id, system_id, valid_until DESC);

DO $$ DECLARE t TEXT; BEGIN
  FOREACH t IN ARRAY ARRAY[
    'irrigation_commissioning_tests_v2',
    'irrigation_commissioning_certificates_v2',
    'irrigation_execution_authorizations_v2'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = NULLIF(current_setting(''app.current_tenant'', true), '''')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting(''app.current_tenant'', true), '''')::uuid)',
      t
    );
  END LOOP;
END $$;

CREATE OR REPLACE FUNCTION sahool_irrx1_commissioning_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'commissioning legal records are append-only; create a superseding record';
END $$;

DROP TRIGGER IF EXISTS irrigation_commissioning_tests_v2_append_only ON irrigation_commissioning_tests_v2;
CREATE TRIGGER irrigation_commissioning_tests_v2_append_only
BEFORE UPDATE OR DELETE ON irrigation_commissioning_tests_v2
FOR EACH ROW EXECUTE FUNCTION sahool_irrx1_commissioning_append_only();

DROP TRIGGER IF EXISTS irrigation_execution_authorizations_v2_append_only ON irrigation_execution_authorizations_v2;
CREATE TRIGGER irrigation_execution_authorizations_v2_append_only
BEFORE UPDATE OR DELETE ON irrigation_execution_authorizations_v2
FOR EACH ROW EXECUTE FUNCTION sahool_irrx1_commissioning_append_only();
