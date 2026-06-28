-- v114_cloud_native_gis_best_practices.sql
-- Phase 4 GIS hardening inspired by farmOS/farmOS-map, TiTiler/Terracotta,
-- GeoParquet, OGC API and STAC/s2cloudless best practices.

CREATE TABLE IF NOT EXISTS raster_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NULL,
    scene_id TEXT NULL,
    product_date DATE NOT NULL,
    index_type TEXT NOT NULL,
    cog_url TEXT NOT NULL,
    tilejson_url TEXT NULL,
    cloud_pct NUMERIC(5,2) DEFAULT 0,
    quality_score INTEGER CHECK (quality_score BETWEEN 0 AND 100),
    resolution_m NUMERIC(6,2) DEFAULT 10,
    bbox JSONB NULL,
    bands JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, field_id, product_date, index_type, cog_url)
);
CREATE INDEX IF NOT EXISTS idx_raster_registry_lookup
    ON raster_registry (tenant_id, field_id, product_date DESC, index_type);
CREATE INDEX IF NOT EXISTS idx_raster_registry_scene
    ON raster_registry (tenant_id, scene_id);

CREATE TABLE IF NOT EXISTS stac_item_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    scene_id TEXT NOT NULL,
    collection TEXT NOT NULL,
    captured_at TIMESTAMPTZ NULL,
    bbox JSONB NULL,
    cloud_pct NUMERIC(5,2) DEFAULT 0,
    quality_score INTEGER CHECK (quality_score BETWEEN 0 AND 100),
    assets JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_item JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, scene_id)
);
CREATE INDEX IF NOT EXISTS idx_stac_item_registry_quality
    ON stac_item_registry (tenant_id, collection, quality_score DESC, captured_at DESC);

CREATE TABLE IF NOT EXISTS geometry_editing_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    user_id UUID NULL,
    viewport JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled_layers JSONB NOT NULL DEFAULT '[]'::jsonb,
    active_tool TEXT NULL,
    undo_stack JSONB NOT NULL DEFAULT '[]'::jsonb,
    redo_stack JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, field_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_geometry_editing_sessions_field
    ON geometry_editing_sessions (tenant_id, field_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS geometry_locks (
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    locked_by UUID NOT NULL,
    locked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    reason TEXT NULL,
    PRIMARY KEY (tenant_id, field_id)
);
CREATE INDEX IF NOT EXISTS idx_geometry_locks_expiry
    ON geometry_locks (expires_at);

ALTER TABLE raster_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE raster_registry FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON raster_registry;
CREATE POLICY tenant_isolation ON raster_registry
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

ALTER TABLE stac_item_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE stac_item_registry FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON stac_item_registry;
CREATE POLICY tenant_isolation ON stac_item_registry
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

ALTER TABLE geometry_editing_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE geometry_editing_sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON geometry_editing_sessions;
CREATE POLICY tenant_isolation ON geometry_editing_sessions
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

ALTER TABLE geometry_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE geometry_locks FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON geometry_locks;
CREATE POLICY tenant_isolation ON geometry_locks
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (NULLIF(current_setting('app.current_tenant', true), '') IS NULL OR tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
