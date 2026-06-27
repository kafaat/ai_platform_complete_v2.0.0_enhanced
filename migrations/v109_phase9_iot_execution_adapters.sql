-- v109: Phase 9 IoT execution adapter runtime.
-- Safe bridge between autonomous execution plans and physical-equipment adapters.
-- No direct device writes happen here; workers/adapters consume audited dispatch rows.

CREATE TABLE IF NOT EXISTS iot_command_dispatch (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    field_id uuid NOT NULL,
    execution_id text NOT NULL,
    dispatch_batch_id text NOT NULL,
    envelope_id text NOT NULL,
    command_id text NOT NULL,
    protocol text NOT NULL,
    target_id text NOT NULL,
    status text NOT NULL,
    physical_effect boolean NOT NULL DEFAULT false,
    reason text,
    adapter_receipt jsonb NOT NULL DEFAULT '{}'::jsonb,
    verification_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, envelope_id)
);

CREATE TABLE IF NOT EXISTS equipment_telemetry_frames (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    field_id uuid,
    target_id text NOT NULL,
    command_id text,
    protocol text,
    observed_at timestamptz NOT NULL DEFAULT now(),
    frame jsonb NOT NULL DEFAULT '{}'::jsonb,
    quality jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_iot_command_dispatch_tenant_field_created
    ON iot_command_dispatch (tenant_id, field_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_iot_command_dispatch_status
    ON iot_command_dispatch (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_equipment_telemetry_frames_target_time
    ON equipment_telemetry_frames (tenant_id, target_id, observed_at DESC);

ALTER TABLE iot_command_dispatch ENABLE ROW LEVEL SECURITY;
ALTER TABLE equipment_telemetry_frames ENABLE ROW LEVEL SECURITY;
ALTER TABLE iot_command_dispatch FORCE ROW LEVEL SECURITY;
ALTER TABLE equipment_telemetry_frames FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='iot_command_dispatch' AND policyname='iot_command_dispatch_tenant_isolation') THEN
        CREATE POLICY iot_command_dispatch_tenant_isolation ON iot_command_dispatch
            USING (tenant_id::text = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='equipment_telemetry_frames' AND policyname='equipment_telemetry_frames_tenant_isolation') THEN
        CREATE POLICY equipment_telemetry_frames_tenant_isolation ON equipment_telemetry_frames
            USING (tenant_id::text = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
    END IF;
END $$;
