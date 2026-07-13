-- M2.10 Irrigation Commissioning & Certification
CREATE TABLE IF NOT EXISTS irrigation_commissioning_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    field_id UUID NOT NULL,
    machine_id UUID NOT NULL,
    evidence_type TEXT NOT NULL CHECK (evidence_type IN (
        'installation_identity','pump_flow_test','pressure_test','controller_handshake',
        'safety_interlock_test','energy_system_test','signed_acceptance'
    )),
    status TEXT NOT NULL CHECK (status IN ('verified','rejected','superseded')),
    observed_at TIMESTAMPTZ NOT NULL,
    captured_by UUID NOT NULL,
    witness_id UUID,
    source_uri TEXT,
    source_hash CHAR(64) NOT NULL,
    values_json JSONB NOT NULL,
    evidence_digest CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, evidence_digest),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id),
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id)
);

CREATE TABLE IF NOT EXISTS irrigation_commissioning_certifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    field_id UUID NOT NULL,
    season_id UUID NOT NULL,
    machine_id UUID NOT NULL,
    controller_id UUID NOT NULL,
    energy_system_id UUID NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft','in_review','certified','expired','revoked','superseded','blocked')),
    operational_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    certified_at TIMESTAMPTZ,
    valid_until TIMESTAMPTZ,
    signed_by UUID,
    reviewed_by UUID,
    certification_scope JSONB NOT NULL,
    irrigation_capability_digest CHAR(64) NOT NULL,
    certification_digest CHAR(64) NOT NULL,
    snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, certification_digest),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id),
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id),
    FOREIGN KEY (controller_id, tenant_id) REFERENCES irrigation_controllers(id, tenant_id),
    FOREIGN KEY (energy_system_id, tenant_id) REFERENCES irrigation_energy_systems(id, tenant_id),
    CHECK (valid_until IS NULL OR certified_at IS NULL OR valid_until > certified_at),
    CHECK (reviewed_by IS NULL OR signed_by IS NULL OR reviewed_by <> signed_by)
);

CREATE TABLE IF NOT EXISTS irrigation_executability_gates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    project_id UUID NOT NULL,
    field_id UUID NOT NULL,
    season_id UUID NOT NULL,
    machine_id UUID NOT NULL,
    irrigation_capability_digest CHAR(64) NOT NULL,
    commissioning_certification_digest CHAR(64) NOT NULL,
    execution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    valid_until TIMESTAMPTZ,
    blocking_reasons JSONB NOT NULL,
    executability_digest CHAR(64) NOT NULL,
    snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, executability_digest),
    FOREIGN KEY (project_id, tenant_id) REFERENCES irrigation_projects(id, tenant_id),
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_commissioning_evidence_latest
    ON irrigation_commissioning_evidence (tenant_id, machine_id, evidence_type, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_commissioning_certification_current
    ON irrigation_commissioning_certifications (tenant_id, machine_id, valid_until DESC)
    WHERE status = 'certified' AND operational_eligible = TRUE;
CREATE INDEX IF NOT EXISTS idx_irrigation_executability_current
    ON irrigation_executability_gates (tenant_id, machine_id, created_at DESC);

DO $$ DECLARE t TEXT; BEGIN
  FOREACH t IN ARRAY ARRAY[
    'irrigation_commissioning_evidence',
    'irrigation_commissioning_certifications',
    'irrigation_executability_gates'
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
