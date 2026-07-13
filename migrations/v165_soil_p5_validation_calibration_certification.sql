BEGIN;
CREATE TABLE IF NOT EXISTS soil_field_validations (
 validation_id text PRIMARY KEY, tenant_id text NOT NULL, field_id text NOT NULL,
 governorate text NOT NULL, crop text, campaign_id text NOT NULL, accepted boolean NOT NULL DEFAULT false,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS soil_regional_calibrations (
 calibration_id text PRIMARY KEY, tenant_id text NOT NULL, field_id text NOT NULL DEFAULT 'regional',
 governorate text NOT NULL, crop text, product_type text NOT NULL, status text NOT NULL,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS soil_production_certifications (
 certification_id text PRIMARY KEY, tenant_id text NOT NULL, field_id text NOT NULL DEFAULT 'release',
 release_ref text NOT NULL, environment text NOT NULL, certified boolean NOT NULL DEFAULT false,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,release_ref,environment));
CREATE TABLE IF NOT EXISTS soil_learning_datasets (
 dataset_id text PRIMARY KEY, tenant_id text NOT NULL, field_id text NOT NULL DEFAULT 'dataset',
 name text NOT NULL, version text NOT NULL, eligible_for_training boolean NOT NULL DEFAULT false,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,name,version));
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['soil_field_validations','soil_regional_calibrations','soil_production_certifications','soil_learning_datasets'] LOOP
 EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t); EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I',t);
 EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.current_tenant'', true)) WITH CHECK (tenant_id = current_setting(''app.current_tenant'', true))',t);
 END LOOP; END $$;
CREATE INDEX IF NOT EXISTS idx_soil_field_validations_scope ON soil_field_validations(tenant_id,field_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_soil_calibrations_region ON soil_regional_calibrations(tenant_id,governorate,product_type,created_at DESC);
COMMIT;
