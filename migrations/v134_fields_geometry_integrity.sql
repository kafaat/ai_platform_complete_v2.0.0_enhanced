-- v134 (v39.5-1 line) — DB-enforced validity for fields.geometry + inline geometry_version.
-- The real draw/PATCH store is fields.geometry (JSONB GeoJSON, v30). The v27 trigger only
-- guards a DIFFERENT table (field_boundaries.geom), and v43's trg_fields_sync_geom derives
-- fields.geom but SWALLOWS invalid GeoJSON (geom := NULL) — so an invalid/self-intersecting
-- polygon written straight into fields.geometry was accepted with NO DB-level rejection.
-- This closes that gap ON THIS table/column and adds a first-class, geometry-specific version:
--   • geometry_version — inline monotonic counter that bumps ONLY when the boundary changes
--     (distinct from fields.row_version which bumps on ANY edit, and from field_state.version
--     which is a projection recompute counter). Lets clients detect stale map overlays without
--     a field_geometry_history join.
--   • BEFORE INSERT/UPDATE trigger — validates via PostGIS ST_IsValid(ST_GeomFromGeoJSON(...))
--     (parse failure treated as invalid) and RAISEs check_violation (SQLSTATE 23514) — same
--     semantics as v27, but on the column the draw path actually writes.
-- Additive + idempotent. fields already has RLS (tenant_id); the new column/trigger inherit it.
-- Does NOT touch v27, v43, v96, or v132. Applied after v132.

ALTER TABLE fields ADD COLUMN IF NOT EXISTS geometry_version INTEGER NOT NULL DEFAULT 1;

CREATE OR REPLACE FUNCTION sahool_enforce_fields_geometry()
RETURNS TRIGGER AS $$
DECLARE
    _geom_changed BOOLEAN;
    _geom geometry;
BEGIN
    -- Fire the body only when the boundary actually changes: on INSERT when geometry is
    -- present, on UPDATE when the JSONB value is semantically distinct (JSONB equality is
    -- normalized ⇒ a no-op rewrite with reordered keys does not bump the version).
    IF TG_OP = 'INSERT' THEN
        _geom_changed := NEW.geometry IS NOT NULL;
    ELSE
        _geom_changed := NEW.geometry IS DISTINCT FROM OLD.geometry;
    END IF;

    IF _geom_changed THEN
        -- (a) validity — only when a geometry is present (skip NULL / geometry removal).
        IF NEW.geometry IS NOT NULL THEN
            -- ST_GeomFromGeoJSON RAISEs on malformed GeoJSON ⇒ treat the parse failure as
            -- invalid geometry (same 23514 as an ST_IsValid failure), never leak a raw error.
            BEGIN
                _geom := ST_GeomFromGeoJSON(NEW.geometry::text);
            EXCEPTION WHEN OTHERS THEN
                RAISE EXCEPTION
                    'هندسة الحقل غير صالحة: GeoJSON غير قابل للتحويل إلى هندسة PostGIS'
                    USING ERRCODE = 'check_violation';
            END;
            IF _geom IS NULL OR NOT ST_IsValid(_geom) THEN
                RAISE EXCEPTION
                    'هندسة الحقل غير صالحة: يجب أن تكون هندسة GeoJSON صالحة (ST_IsValid) غير متقاطعة ذاتيّاً'
                    USING ERRCODE = 'check_violation';
            END IF;
        END IF;

        -- (b) inline, geometry-specific version bump. On INSERT OLD is NULL ⇒ starts at 1
        -- (matches the column DEFAULT); on UPDATE it advances from the prior value.
        NEW.geometry_version := COALESCE(OLD.geometry_version, 0) + 1;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_fields_geometry_integrity ON fields;
CREATE OR REPLACE TRIGGER trg_fields_geometry_integrity
    BEFORE INSERT OR UPDATE ON fields
    FOR EACH ROW EXECUTE FUNCTION sahool_enforce_fields_geometry();

COMMENT ON COLUMN fields.geometry_version IS
    'عدّاد إصدار الحدّ الجزئيّ (inline) — يتزايد فقط حين تتغيّر fields.geometry (يميّزه عن '
    'row_version الذي يرتفع مع أيّ تعديل، وعن field_state.version عدّاد الإسقاط). v134.';
COMMENT ON FUNCTION sahool_enforce_fields_geometry() IS
    'يرفض fields.geometry غير الصالحة (ST_IsValid على ST_GeomFromGeoJSON، فشل التحويل=باطل، '
    'ERRCODE 23514) ويرفع geometry_version عند تغيّر الحدّ فقط — فرض على القاعدة لا API. v134.';
