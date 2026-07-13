-- M2.9 Controller & Edge Adapter Framework
CREATE TABLE IF NOT EXISTS irrigation_controller_handshakes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL,
    controller_id UUID NOT NULL, machine_id UUID NOT NULL, protocol TEXT NOT NULL,
    provider TEXT NOT NULL, model TEXT, firmware_version TEXT,
    integration_mode TEXT NOT NULL CHECK (integration_mode IN ('read_only','dry_run','human_approved_control','guarded_automation')),
    capabilities JSONB NOT NULL, certification_status TEXT NOT NULL,
    identity_fingerprint TEXT NOT NULL, observed_at TIMESTAMPTZ NOT NULL,
    handshake_digest CHAR(64) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, controller_id, handshake_digest),
    FOREIGN KEY (controller_id, tenant_id) REFERENCES irrigation_controllers(id, tenant_id),
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id)
);
CREATE TABLE IF NOT EXISTS irrigation_controller_telemetry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL,
    controller_id UUID NOT NULL, machine_id UUID NOT NULL, sequence_number BIGINT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL, received_at TIMESTAMPTZ NOT NULL,
    source_message_id TEXT NOT NULL, normalized_payload JSONB NOT NULL,
    payload_digest CHAR(64) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, controller_id, sequence_number),
    UNIQUE (tenant_id, controller_id, source_message_id),
    FOREIGN KEY (controller_id, tenant_id) REFERENCES irrigation_controllers(id, tenant_id),
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id),
    CHECK (received_at >= observed_at)
);
CREATE TABLE IF NOT EXISTS canonical_controller_capabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL,
    controller_id UUID NOT NULL, machine_id UUID NOT NULL, status TEXT NOT NULL,
    operational_eligible BOOLEAN NOT NULL, snapshot JSONB NOT NULL,
    capability_digest CHAR(64) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, controller_id, capability_digest),
    FOREIGN KEY (controller_id, tenant_id) REFERENCES irrigation_controllers(id, tenant_id),
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id)
);
CREATE TABLE IF NOT EXISTS irrigation_controller_command_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL,
    controller_id UUID NOT NULL, machine_id UUID NOT NULL, decision_id UUID NOT NULL,
    authorization_id UUID, command_type TEXT NOT NULL, parameters JSONB NOT NULL,
    controller_capability_digest CHAR(64) NOT NULL, command_request_digest CHAR(64) NOT NULL,
    dispatch_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (dispatch_allowed = FALSE),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, command_request_digest),
    FOREIGN KEY (controller_id, tenant_id) REFERENCES irrigation_controllers(id, tenant_id),
    FOREIGN KEY (machine_id, tenant_id) REFERENCES irrigation_machines(id, tenant_id)
);
CREATE INDEX IF NOT EXISTS idx_controller_telemetry_latest ON irrigation_controller_telemetry (tenant_id, controller_id, observed_at DESC);
DO $$ DECLARE t TEXT; BEGIN
  FOREACH t IN ARRAY ARRAY['irrigation_controller_handshakes','irrigation_controller_telemetry','canonical_controller_capabilities','irrigation_controller_command_requests'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id = NULLIF(current_setting(''app.current_tenant'', true), '''')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting(''app.current_tenant'', true), '''')::uuid)', t);
  END LOOP;
END $$;
