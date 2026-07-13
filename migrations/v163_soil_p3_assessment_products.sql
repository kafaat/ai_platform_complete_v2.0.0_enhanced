-- P3 governed products: mobile visual evidence, analog estimation, drainage, reclamation and economics.
CREATE TABLE IF NOT EXISTS soil_visual_observations (
 visual_observation_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT NOT NULL, product_type TEXT NOT NULL,
 version TEXT NOT NULL, identity_hash TEXT NOT NULL, payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,field_id,product_type,version,identity_hash));
CREATE TABLE IF NOT EXISTS soil_analog_products (
 analog_product_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT NOT NULL, product_type TEXT NOT NULL,
 version TEXT NOT NULL, identity_hash TEXT NOT NULL, payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,field_id,product_type,version,identity_hash));
CREATE TABLE IF NOT EXISTS soil_drainage_assessments (
 drainage_assessment_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT NOT NULL, product_type TEXT NOT NULL,
 version TEXT NOT NULL, identity_hash TEXT NOT NULL, payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,field_id,product_type,version,identity_hash));
CREATE TABLE IF NOT EXISTS soil_reclamation_assessments (
 reclamation_assessment_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT NOT NULL, product_type TEXT NOT NULL,
 version TEXT NOT NULL, identity_hash TEXT NOT NULL, payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,field_id,product_type,version,identity_hash));
CREATE TABLE IF NOT EXISTS soil_reclamation_economics (
 economics_product_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT NOT NULL, product_type TEXT NOT NULL,
 version TEXT NOT NULL, identity_hash TEXT NOT NULL, payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,field_id,product_type,version,identity_hash));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['soil_visual_observations','soil_analog_products','soil_drainage_assessments','soil_reclamation_assessments','soil_reclamation_economics'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I',t);
  EXECUTE format($p$CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting('app.current_tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))$p$,t);
  EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I(tenant_id,field_id,updated_at DESC)', 'idx_'||t||'_field', t);
 END LOOP;
END $$;
