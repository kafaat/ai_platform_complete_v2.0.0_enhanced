-- v43: عمود هندسة PostGIS مفهرس (GiST) على fields لتسريع فحص التداخل (ST_Intersects)
-- بدل المسح الخطّيّ مع ST_GeomFromGeoJSON لكلّ صفّ. يُملأ من fields.geometry (JSONB)
-- عبر trigger ويُفهرس GiST. يتطلّب PostGIS (مُفعّل في init_v8). idempotent.
ALTER TABLE fields ADD COLUMN IF NOT EXISTS geom geometry(Geometry, 4326);

-- مزامنة geom من geometry (JSONB) — هندسة تالفة ⇒ NULL (لا نكسر الإدراج).
CREATE OR REPLACE FUNCTION _sahool_fields_sync_geom() RETURNS trigger AS $$
BEGIN
    IF NEW.geometry IS NOT NULL THEN
        BEGIN
            NEW.geom := ST_SetSRID(ST_GeomFromGeoJSON(NEW.geometry::text), 4326);
        EXCEPTION WHEN OTHERS THEN
            NEW.geom := NULL;
        END;
    ELSE
        NEW.geom := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_fields_sync_geom ON fields;
CREATE TRIGGER trg_fields_sync_geom
    BEFORE INSERT OR UPDATE OF geometry ON fields
    FOR EACH ROW EXECUTE FUNCTION _sahool_fields_sync_geom();

-- backfill للصفوف الموجودة (لكلّ صفّ على حدة — هندسة تالفة تُتخطّى بأمان).
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT field_id, geometry FROM fields WHERE geometry IS NOT NULL AND geom IS NULL LOOP
        BEGIN
            UPDATE fields SET geom = ST_SetSRID(ST_GeomFromGeoJSON(r.geometry::text), 4326)
            WHERE field_id = r.field_id;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_fields_geom ON fields USING GIST(geom);
