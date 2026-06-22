-- v96: Spatial geometry integrity hardening.
-- Adds durable geometry revision ledger and raster/indicator cache invalidation queue.
-- Idempotent, tenant-isolated, and safe for local/dev re-runs.

CREATE TABLE IF NOT EXISTS field_geometry_history (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    revision INTEGER NOT NULL,
    geometry JSONB NOT NULL,
    changed_by TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason TEXT NOT NULL DEFAULT 'unspecified',
    source TEXT NOT NULL DEFAULT 'api',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (tenant_id, field_id, revision)
);

CREATE INDEX IF NOT EXISTS idx_field_geometry_history_field
    ON field_geometry_history(tenant_id, field_id, revision DESC);

CREATE OR REPLACE FUNCTION sahool_next_field_geometry_revision()
RETURNS trigger AS $$
BEGIN
    IF NEW.revision IS NULL THEN
        SELECT COALESCE(MAX(revision), 0) + 1
          INTO NEW.revision
          FROM field_geometry_history
         WHERE tenant_id = NEW.tenant_id AND field_id = NEW.field_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_field_geometry_history_revision ON field_geometry_history;
CREATE TRIGGER trg_field_geometry_history_revision
    BEFORE INSERT ON field_geometry_history
    FOR EACH ROW EXECUTE FUNCTION sahool_next_field_geometry_revision();

CREATE TABLE IF NOT EXISTS raster_cache_invalidations (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','processed','failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_raster_cache_invalidations_pending
    ON raster_cache_invalidations(tenant_id, field_id, created_at)
    WHERE status = 'pending';

-- RLS صريح (تفعيل + FORCE + سياسة العزل على current_setting('app.current_tenant'))،
-- لكلّ جدول مستأجِر لاحق للحلقة الشاملة (v70) — نفس نمط v94_scouting_pins تماماً، كي
-- يكتشفه حارس تغطية RLS الساكن (الدالّة المساعِدة غير مرئيّة له). fail-closed.
ALTER TABLE field_geometry_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_geometry_history FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON field_geometry_history;
CREATE POLICY tenant_isolation ON field_geometry_history
    USING (
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    )
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

ALTER TABLE raster_cache_invalidations ENABLE ROW LEVEL SECURITY;
ALTER TABLE raster_cache_invalidations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON raster_cache_invalidations;
CREATE POLICY tenant_isolation ON raster_cache_invalidations
    USING (
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    )
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
