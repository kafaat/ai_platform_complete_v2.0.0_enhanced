-- SAHOOL v14 — migrations/v14_imagery_storage.sql
-- ─────────────────────────────────────────────────────────────────────────
-- تخزين الصور المعالَجة: سجلّ الراستر (COG/GeoTIFF)، مناطق الإدارة الزراعيّة،
-- وإحصاءات المناطق لكلّ مؤشّر/تاريخ. كلّ الجداول idempotent (IF NOT EXISTS)،
-- تحمل tenant_id، مع RLS مُفعَّل وسياسة عزل مستأجر موحّدة. الفرض النهائي (FORCE)
-- يتمّ في v9_rls_force_all (يجب أن يبقى أخيراً في MANIFEST بعد هذا الملفّ).
-- ─────────────────────────────────────────────────────────────────────────

-- ── سجلّ الراستر COG/GeoTIFF ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raster_assets (
    id                  BIGSERIAL PRIMARY KEY,
    field_id            VARCHAR(50)  NOT NULL,
    tenant_id           UUID,
    scene_id            VARCHAR(200),
    acquisition_date    DATE,
    satellite           VARCHAR(50),
    index_name          VARCHAR(30),
    cloud_pct           NUMERIC,
    srid                INT          DEFAULT 4326,
    cog_uri             TEXT,
    bands               JSONB,
    nodata              DOUBLE PRECISION,
    footprint           GEOMETRY(POLYGON, 4326),
    provenance          JSONB,
    processing_job_id   VARCHAR(100),
    created_at          TIMESTAMPTZ  DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_raster_field_date
    ON raster_assets (field_id, acquisition_date DESC);
CREATE INDEX IF NOT EXISTS idx_raster_footprint
    ON raster_assets USING GIST (footprint);

ALTER TABLE raster_assets ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON raster_assets;
CREATE POLICY tenant_isolation ON raster_assets
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''));

-- ── مناطق الإدارة (التقسيم الزونيّ) ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS management_zones (
    id              BIGSERIAL PRIMARY KEY,
    zone_id         VARCHAR(100),
    field_id        VARCHAR(50)  NOT NULL,
    tenant_id       UUID,
    geom            GEOMETRY(POLYGON, 4326),
    classification  VARCHAR(50),
    mean_value      NUMERIC,
    source          VARCHAR(50),
    created_at      TIMESTAMPTZ  DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mgmt_zones_field
    ON management_zones (field_id);
CREATE INDEX IF NOT EXISTS idx_mgmt_zones_geom
    ON management_zones USING GIST (geom);

ALTER TABLE management_zones ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON management_zones;
CREATE POLICY tenant_isolation ON management_zones
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''));

-- ── إحصاءات المناطق لكلّ مؤشّر/تاريخ ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS zonal_stats (
    id              BIGSERIAL PRIMARY KEY,
    zone_id         VARCHAR(100),
    field_id        VARCHAR(50)  NOT NULL,
    tenant_id       UUID,
    index_name      VARCHAR(30),
    stat_date       DATE,
    mean            NUMERIC,
    min             NUMERIC,
    max             NUMERIC,
    std             NUMERIC,
    pixel_count     INT,
    created_at      TIMESTAMPTZ  DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_zonal_stats_field_index_date
    ON zonal_stats (field_id, index_name, stat_date DESC);

ALTER TABLE zonal_stats ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON zonal_stats;
CREATE POLICY tenant_isolation ON zonal_stats
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''));
