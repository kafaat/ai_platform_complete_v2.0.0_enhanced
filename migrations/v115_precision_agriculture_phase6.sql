-- Phase 6 precision agriculture intelligence durable artifacts.
-- Keeps AI outputs tenant-scoped and auditable.  Heavy ML artifacts remain in object storage.

CREATE TABLE IF NOT EXISTS boundary_extraction_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    field_id text NOT NULL,
    imagery_id text,
    model text NOT NULL DEFAULT 'sam2-geosam',
    seed_geometry jsonb,
    result_geometry jsonb,
    confidence numeric(5,2),
    area_ha numeric(14,4),
    status text NOT NULL DEFAULT 'pending',
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_boundary_jobs_tenant_field ON boundary_extraction_jobs (tenant_id, field_id, created_at DESC);

CREATE TABLE IF NOT EXISTS management_zone_sets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    field_id text NOT NULL,
    source_layers jsonb NOT NULL DEFAULT '[]'::jsonb,
    algorithm text NOT NULL,
    n_zones int NOT NULL CHECK (n_zones BETWEEN 2 AND 7),
    summary jsonb NOT NULL,
    features jsonb NOT NULL,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_management_zone_sets_tenant_field ON management_zone_sets (tenant_id, field_id, created_at DESC);

CREATE TABLE IF NOT EXISTS prescription_maps (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    field_id text NOT NULL,
    zone_set_id uuid REFERENCES management_zone_sets(id) ON DELETE SET NULL,
    crop text NOT NULL,
    prescription_type text NOT NULL,
    unit text NOT NULL,
    payload jsonb NOT NULL,
    export_formats jsonb NOT NULL DEFAULT '["GeoJSON"]'::jsonb,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prescription_maps_tenant_field ON prescription_maps (tenant_id, field_id, crop, prescription_type, created_at DESC);

CREATE TABLE IF NOT EXISTS yield_stability_maps (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    field_id text NOT NULL,
    years int NOT NULL DEFAULT 0,
    payload jsonb NOT NULL,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS farm_digital_twin_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    farm_id text NOT NULL,
    snapshot_id text NOT NULL,
    health_score int NOT NULL CHECK (health_score BETWEEN 0 AND 100),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, snapshot_id)
);

ALTER TABLE boundary_extraction_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE management_zone_sets ENABLE ROW LEVEL SECURITY;
ALTER TABLE prescription_maps ENABLE ROW LEVEL SECURITY;
ALTER TABLE yield_stability_maps ENABLE ROW LEVEL SECURITY;
ALTER TABLE farm_digital_twin_snapshots ENABLE ROW LEVEL SECURITY;

ALTER TABLE boundary_extraction_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE management_zone_sets FORCE ROW LEVEL SECURITY;
ALTER TABLE prescription_maps FORCE ROW LEVEL SECURITY;
ALTER TABLE yield_stability_maps FORCE ROW LEVEL SECURITY;
ALTER TABLE farm_digital_twin_snapshots FORCE ROW LEVEL SECURITY;

-- سياسات عزل المستأجِر الصريحة (تطابق _sahool_apply_tenant_rls في v9):
-- USING فشل-مغلق عند سياق فارغ؛ WITH CHECK يمنع الكتابة عابرة المستأجِر.
DROP POLICY IF EXISTS boundary_extraction_jobs_tenant_isolation ON boundary_extraction_jobs;
CREATE POLICY boundary_extraction_jobs_tenant_isolation ON boundary_extraction_jobs
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
DROP POLICY IF EXISTS management_zone_sets_tenant_isolation ON management_zone_sets;
CREATE POLICY management_zone_sets_tenant_isolation ON management_zone_sets
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
DROP POLICY IF EXISTS prescription_maps_tenant_isolation ON prescription_maps;
CREATE POLICY prescription_maps_tenant_isolation ON prescription_maps
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
DROP POLICY IF EXISTS yield_stability_maps_tenant_isolation ON yield_stability_maps;
CREATE POLICY yield_stability_maps_tenant_isolation ON yield_stability_maps
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
DROP POLICY IF EXISTS farm_digital_twin_snapshots_tenant_isolation ON farm_digital_twin_snapshots;
CREATE POLICY farm_digital_twin_snapshots_tenant_isolation ON farm_digital_twin_snapshots
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
