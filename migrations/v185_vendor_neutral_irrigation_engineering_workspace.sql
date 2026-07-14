-- IRR-X1: vendor-neutral irrigation system specifications and immutable calculation snapshots.
CREATE TABLE IF NOT EXISTS irrigation_system_specifications (
    specification_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    season_id TEXT,
    system_id TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    specification JSONB NOT NULL,
    content_digest TEXT NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    supersedes_specification_id TEXT REFERENCES irrigation_system_specifications(specification_id),
    UNIQUE (tenant_id, system_id, content_digest)
);

CREATE TABLE IF NOT EXISTS irrigation_engineering_calculations (
    calculation_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    season_id TEXT,
    system_id TEXT NOT NULL,
    specification_digest TEXT NOT NULL CHECK (specification_digest ~ '^[0-9a-f]{64}$'),
    water_demand_digest TEXT NOT NULL CHECK (water_demand_digest ~ '^[0-9a-f]{64}$'),
    result JSONB NOT NULL,
    content_digest TEXT NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, system_id, content_digest)
);

ALTER TABLE irrigation_system_specifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE irrigation_system_specifications FORCE ROW LEVEL SECURITY;
ALTER TABLE irrigation_engineering_calculations ENABLE ROW LEVEL SECURITY;
ALTER TABLE irrigation_engineering_calculations FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS irrigation_system_specifications_tenant_isolation ON irrigation_system_specifications;
CREATE POLICY irrigation_system_specifications_tenant_isolation ON irrigation_system_specifications
USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

DROP POLICY IF EXISTS irrigation_engineering_calculations_tenant_isolation ON irrigation_engineering_calculations;
CREATE POLICY irrigation_engineering_calculations_tenant_isolation ON irrigation_engineering_calculations
USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

CREATE OR REPLACE FUNCTION sahool_irrx1_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'IRR-X1 engineering records are append-only; create a superseding record';
END $$;

DROP TRIGGER IF EXISTS irrigation_system_specifications_append_only ON irrigation_system_specifications;
CREATE TRIGGER irrigation_system_specifications_append_only
BEFORE UPDATE OR DELETE ON irrigation_system_specifications
FOR EACH ROW EXECUTE FUNCTION sahool_irrx1_append_only();

DROP TRIGGER IF EXISTS irrigation_engineering_calculations_append_only ON irrigation_engineering_calculations;
CREATE TRIGGER irrigation_engineering_calculations_append_only
BEFORE UPDATE OR DELETE ON irrigation_engineering_calculations
FOR EACH ROW EXECUTE FUNCTION sahool_irrx1_append_only();
