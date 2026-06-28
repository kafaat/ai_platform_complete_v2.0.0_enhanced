-- v104: harden POST /api/v1/fields create contract
-- Fixes runtime 503 during field creation on existing databases where earlier
-- migrations stopped before adding derived/projection columns. Idempotent.

BEGIN;

-- Base fields columns used by routers/fields.py INSERT and field_state_projection.py.
ALTER TABLE fields ADD COLUMN IF NOT EXISTS farm_id VARCHAR(50);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS manager VARCHAR(100);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS geometry JSONB;
ALTER TABLE fields ADD COLUMN IF NOT EXISTS field_code VARCHAR(50);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE fields ADD COLUMN IF NOT EXISTS water_source VARCHAR(20);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS irrigation_type VARCHAR(20);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS ownership_type VARCHAR(20);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS country VARCHAR(60);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS region VARCHAR(80);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS planting_date DATE;

CREATE INDEX IF NOT EXISTS idx_fields_tenant ON fields(tenant_id);
CREATE INDEX IF NOT EXISTS idx_fields_farm ON fields(farm_id);

-- Optional FK to farms, only when farms exists and the constraint is absent.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'farms')
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fields_farm_id') THEN
        ALTER TABLE fields
            ADD CONSTRAINT fk_fields_farm_id
            FOREIGN KEY (farm_id) REFERENCES farms(farm_id) ON DELETE SET NULL NOT VALID;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Skipping fk_fields_farm_id: %', SQLERRM;
END $$;

-- field_state projection table/column safety for recompute_field_state.
CREATE TABLE IF NOT EXISTS field_state (
    field_id           VARCHAR(50) PRIMARY KEY,
    tenant_id          UUID NOT NULL,
    validity           VARCHAR(16) NOT NULL,
    execution_mode     VARCHAR(16) NOT NULL,
    confidence_level   VARCHAR(16),
    ndvi_age_days      DOUBLE PRECISION,
    soil_age_days      DOUBLE PRECISION,
    weather_age_hours  DOUBLE PRECISION,
    reasons_ar         JSONB NOT NULL DEFAULT '[]'::jsonb,
    conflicts          JSONB NOT NULL DEFAULT '[]'::jsonb,
    freshness_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    inputs             JSONB NOT NULL DEFAULT '{}'::jsonb,
    agronomic          JSONB,
    computed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE field_state ADD COLUMN IF NOT EXISTS agronomic JSONB;
ALTER TABLE field_state ADD COLUMN IF NOT EXISTS inputs JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE field_state ADD COLUMN IF NOT EXISTS reasons_ar JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE field_state ADD COLUMN IF NOT EXISTS conflicts JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE field_state ADD COLUMN IF NOT EXISTS freshness_warnings JSONB NOT NULL DEFAULT '[]'::jsonb;

-- field_state is tenant-scoped and created after v70 propagate; apply RLS/FORCE explicitly.
DO $$
BEGIN
    IF to_regproc('_sahool_apply_tenant_rls') IS NOT NULL THEN
        PERFORM _sahool_apply_tenant_rls('field_state');
    ELSE
        ALTER TABLE field_state ENABLE ROW LEVEL SECURITY;
        ALTER TABLE field_state FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation ON field_state;
        CREATE POLICY tenant_isolation ON field_state
            USING (tenant_id::text = current_setting('app.current_tenant', true))
            WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));
    END IF;
END $$;

-- PostGIS geom acceleration is optional. Create only when the extension is available.
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS postgis;
    ALTER TABLE fields ADD COLUMN IF NOT EXISTS geom geometry(Geometry, 4326);
    CREATE INDEX IF NOT EXISTS idx_fields_geom ON fields USING GIST(geom);
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'PostGIS not available; field creation will still store GeoJSON geometry: %', SQLERRM;
END $$;

COMMIT;
