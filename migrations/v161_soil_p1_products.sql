-- P1 governed soil products: SoilGrids spatial baseline, sampling, hydraulics, irrigation water.
CREATE TABLE IF NOT EXISTS soil_spatial_products (
  product_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT NOT NULL,
  product_type TEXT NOT NULL, dataset_version TEXT NOT NULL, geometry_hash TEXT NOT NULL,
  payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(tenant_id, field_id, product_type, dataset_version, geometry_hash)
);
CREATE TABLE IF NOT EXISTS soil_sampling_plans (
  plan_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft', mode TEXT NOT NULL, payload JSONB NOT NULL,
  approved_by TEXT, approved_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS soil_hydraulic_profiles (
  hydraulic_profile_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT NOT NULL,
  source_soil_profile_hash TEXT NOT NULL, payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(tenant_id, field_id, source_soil_profile_hash)
);
CREATE TABLE IF NOT EXISTS irrigation_water_samples (
  sample_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT, source_id TEXT NOT NULL,
  sampled_at TIMESTAMPTZ NOT NULL, approved BOOLEAN NOT NULL DEFAULT FALSE,
  payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS irrigation_water_profiles (
  water_profile_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT, source_id TEXT NOT NULL,
  sample_id TEXT NOT NULL REFERENCES irrigation_water_samples(sample_id),
  payload JSONB NOT NULL, effective_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(tenant_id, sample_id)
);
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['soil_spatial_products','soil_sampling_plans','soil_hydraulic_profiles','irrigation_water_samples','irrigation_water_profiles'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I',t);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting('app.current_tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))$p$,t);
  END LOOP;
END $$;
CREATE INDEX IF NOT EXISTS idx_soil_spatial_products_field ON soil_spatial_products(tenant_id,field_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_soil_sampling_plans_field ON soil_sampling_plans(tenant_id,field_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_soil_hydraulic_profiles_field ON soil_hydraulic_profiles(tenant_id,field_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_irrigation_water_profiles_source ON irrigation_water_profiles(tenant_id,source_id,effective_at DESC);
