-- v154 — durable raster product identity + recoverable batch leases.
--
-- Product identity must include algorithm/mask/geometry versions. The v145 index
-- only covered tenant+field+indicator+date+scene, which incorrectly collapsed a
-- legitimate reprocess with a new algorithm or field geometry into the old row.

BEGIN;

ALTER TABLE raster_assets
    ADD COLUMN IF NOT EXISTS product_identity_key TEXT,
    ADD COLUMN IF NOT EXISTS algorithm_version TEXT,
    ADD COLUMN IF NOT EXISTS qa_mask_version TEXT,
    ADD COLUMN IF NOT EXISTS field_geometry_hash TEXT;

-- Legacy rows receive a deterministic legacy identity. New writers provide the
-- full SHA-256 identity from the application contract.
UPDATE raster_assets
SET algorithm_version = COALESCE(algorithm_version, 'legacy.unknown'),
    field_geometry_hash = COALESCE(field_geometry_hash, 'legacy.geometry'),
    product_identity_key = COALESCE(
        product_identity_key,
        'rip_legacy_' || md5(
            COALESCE(tenant_id::text, '') || '|' || field_id || '|' ||
            COALESCE(scene_id, '') || '|' || index_name || '|' ||
            COALESCE(acquisition_date::text, '') || '|' ||
            COALESCE(algorithm_version, 'legacy.unknown') || '|' ||
            COALESCE(qa_mask_version, '') || '|' ||
            COALESCE(field_geometry_hash, 'legacy.geometry')
        )
    )
WHERE product_identity_key IS NULL;

DROP INDEX IF EXISTS uq_raster_assets_product;
CREATE UNIQUE INDEX IF NOT EXISTS uq_raster_assets_product_identity
    ON raster_assets (product_identity_key)
    WHERE product_identity_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_raster_assets_product_lookup
    ON raster_assets (
        tenant_id, field_id, index_name, scene_id,
        algorithm_version, qa_mask_version, field_geometry_hash
    );

CREATE TABLE IF NOT EXISTS raster_batch_jobs (
    claim_key           TEXT PRIMARY KEY,
    job_id              TEXT NOT NULL UNIQUE,
    tenant_id           UUID NOT NULL,
    field_id            VARCHAR(50),
    status              TEXT NOT NULL DEFAULT 'pending',
    lease_owner         TEXT,
    lease_token         TEXT,
    lease_expires_at    TIMESTAMPTZ,
    request_payload     JSONB NOT NULL,
    result_payload      JSONB,
    error_code          TEXT,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    CONSTRAINT chk_raster_batch_status CHECK (
        status IN ('pending','processing','completed','failed')
    )
);

ALTER TABLE raster_batch_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE raster_batch_jobs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON raster_batch_jobs;
CREATE POLICY tenant_isolation ON raster_batch_jobs
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''));

CREATE INDEX IF NOT EXISTS idx_raster_batch_jobs_reclaim
    ON raster_batch_jobs (status, lease_expires_at)
    WHERE status IN ('pending','processing');
CREATE INDEX IF NOT EXISTS idx_raster_batch_jobs_tenant_updated
    ON raster_batch_jobs (tenant_id, updated_at DESC);

COMMIT;
