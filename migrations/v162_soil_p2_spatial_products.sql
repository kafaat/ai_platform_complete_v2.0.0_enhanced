-- P2 governed spatial products: bare soil, terrain, texture probabilities, salinity/gypsum/carbonate.
CREATE TABLE IF NOT EXISTS soil_bare_composites (
 composite_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT NOT NULL, product_type TEXT NOT NULL,
 version TEXT NOT NULL, geometry_hash TEXT NOT NULL, payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,field_id,product_type,version,geometry_hash));
CREATE TABLE IF NOT EXISTS soil_terrain_products (
 terrain_product_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT NOT NULL, product_type TEXT NOT NULL,
 version TEXT NOT NULL, geometry_hash TEXT NOT NULL, payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,field_id,product_type,version,geometry_hash));
CREATE TABLE IF NOT EXISTS soil_texture_products (
 texture_product_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT NOT NULL, product_type TEXT NOT NULL,
 version TEXT NOT NULL, geometry_hash TEXT NOT NULL, payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,field_id,product_type,version,geometry_hash));
CREATE TABLE IF NOT EXISTS soil_salinity_products (
 salinity_product_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, field_id TEXT NOT NULL, product_type TEXT NOT NULL,
 version TEXT NOT NULL, geometry_hash TEXT NOT NULL, payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,field_id,product_type,version,geometry_hash));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['soil_bare_composites','soil_terrain_products','soil_texture_products','soil_salinity_products'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I',t);
  EXECUTE format($p$CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting('app.current_tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))$p$,t);
  EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I(tenant_id,field_id,updated_at DESC)', 'idx_'||t||'_field', t);
 END LOOP;
END $$;
