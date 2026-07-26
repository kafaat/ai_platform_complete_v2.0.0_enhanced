-- v215 / PA-003: real yield-map ingestion truth.
--
-- Distinct from yield analysis: this migration persists actual geospatial harvest
-- measurements.  The parent ingestion carries source provenance and a tenant-scoped
-- idempotency key; child records are immutable PostGIS points with per-record digests.
-- Both tables are FORCE-RLS and bind field ownership with a composite FK.
BEGIN;

CREATE TABLE IF NOT EXISTS yield_map_ingestions (
    ingestion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    season_id VARCHAR(50),
    source_name VARCHAR(255) NOT NULL,
    source_format TEXT NOT NULL CHECK (source_format IN ('csv','geojson')),
    source_crs TEXT NOT NULL DEFAULT 'EPSG:4326' CHECK (source_crs = 'EPSG:4326'),
    source_sha256 CHAR(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    parser_version TEXT NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    record_count INTEGER NOT NULL DEFAULT 0 CHECK (record_count >= 0),
    min_yield_kg_ha DOUBLE PRECISION,
    max_yield_kg_ha DOUBLE PRECISION,
    mean_yield_kg_ha DOUBLE PRECISION,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, ingestion_id),
    UNIQUE (tenant_id, ingestion_id, field_id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, field_id)
        REFERENCES fields (tenant_id, field_id) ON DELETE RESTRICT,
    FOREIGN KEY (season_id)
        REFERENCES seasons (season_id) ON DELETE RESTRICT,
    CHECK (min_yield_kg_ha IS NULL OR min_yield_kg_ha > 0),
    CHECK (max_yield_kg_ha IS NULL OR max_yield_kg_ha > 0),
    CHECK (mean_yield_kg_ha IS NULL OR mean_yield_kg_ha > 0),
    CHECK (
        min_yield_kg_ha IS NULL OR max_yield_kg_ha IS NULL OR
        min_yield_kg_ha <= max_yield_kg_ha
    )
);

CREATE TABLE IF NOT EXISTS yield_map_records (
    record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    ingestion_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    season_id VARCHAR(50),
    source_record_id VARCHAR(160) NOT NULL,
    geom geometry(Point, 4326) NOT NULL,
    yield_kg_ha DOUBLE PRECISION NOT NULL CHECK (yield_kg_ha > 0 AND yield_kg_ha <= 100000),
    moisture_pct DOUBLE PRECISION CHECK (
        moisture_pct IS NULL OR (moisture_pct >= 0 AND moisture_pct <= 100)
    ),
    harvested_at TIMESTAMPTZ,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    record_sha256 CHAR(64) NOT NULL CHECK (record_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, ingestion_id, source_record_id),
    UNIQUE (tenant_id, ingestion_id, record_sha256),
    FOREIGN KEY (tenant_id, ingestion_id, field_id)
        REFERENCES yield_map_ingestions (tenant_id, ingestion_id, field_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_yield_map_ingestions_field
    ON yield_map_ingestions (tenant_id, field_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_yield_map_ingestions_season
    ON yield_map_ingestions (tenant_id, season_id, created_at DESC)
    WHERE season_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_yield_map_records_field
    ON yield_map_records (tenant_id, field_id, harvested_at DESC);
CREATE INDEX IF NOT EXISTS ix_yield_map_records_ingestion
    ON yield_map_records (tenant_id, ingestion_id, source_record_id);
CREATE INDEX IF NOT EXISTS ix_yield_map_records_geom
    ON yield_map_records USING GIST (geom);

ALTER TABLE yield_map_ingestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE yield_map_ingestions FORCE ROW LEVEL SECURITY;
ALTER TABLE yield_map_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE yield_map_records FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON yield_map_ingestions;
CREATE POLICY tenant_isolation ON yield_map_ingestions
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
DROP POLICY IF EXISTS tenant_isolation ON yield_map_records;
CREATE POLICY tenant_isolation ON yield_map_records
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

CREATE OR REPLACE FUNCTION yield_map_validate_scope() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.season_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM seasons s
         WHERE s.season_id=NEW.season_id
           AND s.tenant_id=NEW.tenant_id
           AND s.field_id=NEW.field_id
    ) THEN
        RAISE EXCEPTION 'yield-map season must belong to the same tenant and field';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_yield_map_validate_scope ON yield_map_ingestions;
CREATE TRIGGER trg_yield_map_validate_scope
    BEFORE INSERT ON yield_map_ingestions
    FOR EACH ROW EXECUTE FUNCTION yield_map_validate_scope();

-- Batch-level invariant: every inserted point must be covered by the authorized
-- field geometry and repeat the parent ingestion season exactly.  A transition
-- table keeps this set-based for large combine files instead of one lookup per row.
CREATE OR REPLACE FUNCTION yield_map_validate_record_batch() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM new_yield_records r
          JOIN yield_map_ingestions i
            ON i.tenant_id=r.tenant_id
           AND i.ingestion_id=r.ingestion_id
           AND i.field_id=r.field_id
          JOIN fields f
            ON f.tenant_id=r.tenant_id
           AND f.field_id=r.field_id
         WHERE i.season_id IS DISTINCT FROM r.season_id
            OR f.geom IS NULL
            OR NOT ST_Covers(f.geom, r.geom)
    ) THEN
        RAISE EXCEPTION 'yield-map records must match the parent season and remain inside the field';
    END IF;
    RETURN NULL;
END;
$$;
DROP TRIGGER IF EXISTS trg_yield_map_validate_record_batch ON yield_map_records;
CREATE TRIGGER trg_yield_map_validate_record_batch
    AFTER INSERT ON yield_map_records
    REFERENCING NEW TABLE AS new_yield_records
    FOR EACH STATEMENT EXECUTE FUNCTION yield_map_validate_record_batch();

-- Yield measurements are evidence.  Corrections are new ingestions, never mutation or
-- deletion of the source-backed record set.
CREATE OR REPLACE FUNCTION yield_map_forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'yield-map evidence is append-only; submit a corrected ingestion';
END;
$$;
DROP TRIGGER IF EXISTS trg_yield_map_ingestions_immutable ON yield_map_ingestions;
CREATE TRIGGER trg_yield_map_ingestions_immutable
    BEFORE UPDATE OR DELETE ON yield_map_ingestions
    FOR EACH ROW EXECUTE FUNCTION yield_map_forbid_mutation();
DROP TRIGGER IF EXISTS trg_yield_map_records_immutable ON yield_map_records;
CREATE TRIGGER trg_yield_map_records_immutable
    BEFORE UPDATE OR DELETE ON yield_map_records
    FOR EACH ROW EXECUTE FUNCTION yield_map_forbid_mutation();

COMMENT ON TABLE yield_map_ingestions IS
    'PA-003 immutable yield-map source/provenance batches with tenant-scoped idempotency.';
COMMENT ON TABLE yield_map_records IS
    'PA-003 canonical geospatial yield observations (PostGIS Point 4326), append-only.';

COMMIT;
