-- v216 / INT-004 (adapter slice): persisted machinery-integration adapter.
--
-- Two concerns, both tenant-scoped + FORCE-RLS:
--   1. machine_control_profiles — the SYSTEM OF RECORD for controller capability
--      profiles (vendor/model/firmware/units/ISOXML support). Resolved by a stable
--      id at export time; a missing/inactive/tenant-mismatched/incompatible profile
--      fails closed. Mutable (may be edited/deactivated), so no immutability trigger.
--   2. machinery_export_artifacts — the durable, APPEND-ONLY record of a produced
--      machine-uploadable ISOXML package: an immutable snapshot of the resolved
--      profile (so a later profile edit cannot change the meaning of an existing
--      export), the packaged bytes, and a content checksum. Corrections are new
--      artifacts, never mutation.
--
-- Honest boundary: this persists the machine-UPLOADABLE artifact at the platform
-- edge. It does NOT connect to a controller, transmit over CAN/ISOBUS, or claim a
-- machine consumed/executed the task — no device-delivery/runtime claim here.
BEGIN;

-- equipment (v23) is PK on equipment_id alone; a composite FK on
-- (tenant_id, equipment_id) needs a matching unique key. Adding it makes the
-- optional profile→equipment link tenant-safe (a profile cannot point at another
-- tenant's machine) without weakening the existing PK. Idempotent via catalog guard.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'equipment_tenant_equipment_uk' AND conrelid = 'equipment'::regclass
    ) THEN
        ALTER TABLE equipment ADD CONSTRAINT equipment_tenant_equipment_uk
            UNIQUE (tenant_id, equipment_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS machine_control_profiles (
    profile_id VARCHAR(64) NOT NULL,
    tenant_id UUID NOT NULL,
    equipment_id VARCHAR(50),
    vendor TEXT NOT NULL,
    controller_model TEXT NOT NULL,
    firmware_version TEXT,
    task_controller_version TEXT NOT NULL,
    unit_system TEXT NOT NULL DEFAULT 'metric' CHECK (unit_system IN ('metric', 'imperial', 'mixed')),
    supported_units JSONB NOT NULL DEFAULT '[]'::jsonb,
    supports_isoxml BOOLEAN NOT NULL DEFAULT true,
    active BOOLEAN NOT NULL DEFAULT true,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id),
    UNIQUE (tenant_id, profile_id),
    FOREIGN KEY (tenant_id, equipment_id)
        REFERENCES equipment (tenant_id, equipment_id) ON DELETE SET NULL,
    CHECK (jsonb_typeof(supported_units) = 'array')
);

CREATE TABLE IF NOT EXISTS machinery_export_artifacts (
    artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    prescription_id VARCHAR(128) NOT NULL,
    machine_profile_id VARCHAR(64) NOT NULL,
    export_format TEXT NOT NULL DEFAULT 'isoxml' CHECK (export_format IN ('isoxml')),
    profile_snapshot JSONB NOT NULL,
    package_sha256 CHAR(64) NOT NULL CHECK (package_sha256 ~ '^[0-9a-f]{64}$'),
    package_bytes BYTEA NOT NULL,
    package_bytes_len INTEGER NOT NULL CHECK (package_bytes_len > 0),
    zone_count INTEGER NOT NULL CHECK (zone_count > 0),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, artifact_id),
    FOREIGN KEY (tenant_id, field_id)
        REFERENCES fields (tenant_id, field_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, machine_profile_id)
        REFERENCES machine_control_profiles (tenant_id, profile_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_machine_profiles_tenant_active
    ON machine_control_profiles (tenant_id, active);
CREATE INDEX IF NOT EXISTS ix_machine_profiles_equipment
    ON machine_control_profiles (tenant_id, equipment_id)
    WHERE equipment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_machinery_artifacts_prescription
    ON machinery_export_artifacts (tenant_id, prescription_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_machinery_artifacts_field
    ON machinery_export_artifacts (tenant_id, field_id, created_at DESC);

ALTER TABLE machine_control_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE machine_control_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE machinery_export_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE machinery_export_artifacts FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON machine_control_profiles;
CREATE POLICY tenant_isolation ON machine_control_profiles
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
DROP POLICY IF EXISTS tenant_isolation ON machinery_export_artifacts;
CREATE POLICY tenant_isolation ON machinery_export_artifacts
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

CREATE OR REPLACE FUNCTION machine_profiles_touch_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_machine_profiles_updated_at ON machine_control_profiles;
CREATE TRIGGER trg_machine_profiles_updated_at
    BEFORE UPDATE ON machine_control_profiles
    FOR EACH ROW EXECUTE FUNCTION machine_profiles_touch_updated_at();

-- A produced package is provenance evidence: append-only. A regeneration is a new
-- artifact (fresh id/checksum/snapshot), never mutation of an existing one.
CREATE OR REPLACE FUNCTION machinery_artifacts_forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'machinery export artifacts are append-only; regenerate to correct';
END;
$$;
DROP TRIGGER IF EXISTS trg_machinery_artifacts_immutable ON machinery_export_artifacts;
CREATE TRIGGER trg_machinery_artifacts_immutable
    BEFORE UPDATE OR DELETE ON machinery_export_artifacts
    FOR EACH ROW EXECUTE FUNCTION machinery_artifacts_forbid_mutation();

COMMENT ON TABLE machine_control_profiles IS
    'INT-004 system of record for controller capability profiles (tenant-scoped, FORCE-RLS).';
COMMENT ON TABLE machinery_export_artifacts IS
    'INT-004 durable append-only machine-uploadable ISOXML packages with immutable profile snapshot + checksum.';

COMMIT;
