-- v105_enterprise_imagery_best_practices.sql
-- Enterprise imagery hardening: geometry versioning, explicit AOI quality metadata,
-- and export-friendly indexes. Idempotent and safe to re-run.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS field_geometry_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    field_id text NOT NULL,
    tenant_id uuid NOT NULL,
    geometry geometry(Geometry, 4326) NOT NULL,
    valid_from timestamptz NOT NULL DEFAULT now(),
    valid_to timestamptz NULL,
    reason text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ST_IsValid(geometry)),
    CHECK (GeometryType(geometry) IN ('POLYGON','MULTIPOLYGON'))
);

CREATE INDEX IF NOT EXISTS idx_field_geometry_versions_tenant_field
    ON field_geometry_versions (tenant_id, field_id, valid_from DESC);

CREATE INDEX IF NOT EXISTS idx_field_geometry_versions_geom
    ON field_geometry_versions USING GIST (geometry);

ALTER TABLE field_geometry_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_geometry_versions FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = current_schema()
          AND tablename = 'field_geometry_versions'
          AND policyname = 'field_geometry_versions_tenant_isolation'
    ) THEN
        CREATE POLICY field_geometry_versions_tenant_isolation
        ON field_geometry_versions
        USING (tenant_id::text = current_setting('app.current_tenant', true))
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true));
    END IF;
END $$;

ALTER TABLE raster_assets ADD COLUMN IF NOT EXISTS aoi_cloud_pct double precision;
ALTER TABLE raster_assets ADD COLUMN IF NOT EXISTS quality_score double precision;
ALTER TABLE raster_assets ADD COLUMN IF NOT EXISTS cloud_mask_sources jsonb DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_raster_assets_quality_pick
    ON raster_assets (tenant_id, field_id, index_name, acquisition_date DESC, cloud_pct ASC);
