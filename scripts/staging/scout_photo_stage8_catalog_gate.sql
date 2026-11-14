-- Read-only catalog acceptance gate for a staging PostgreSQL 15+ DB.
-- No fixture writes and no secret values embedded in this file.
-- Live role/RLS/data isolation tests remain separate mandatory acceptance.
\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
DO $$
DECLARE
  object_name text;
  rel_oid oid;
  role_name text;
  obj text;
  needed_trigger text;
  kind text;
BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'scout-photo catalog gate requires PG15+';
  END IF;
  FOREACH object_name IN ARRAY ARRAY[
    'scout_photo_evidence','scout_photo_season_link_events',
    'scout_photo_field_access_grants','scout_photo_grant_audit_events',
    'scout_photo_detection_link_events','detection_provenance'
  ] LOOP
    rel_oid := to_regclass('public.' || object_name);
    IF rel_oid IS NULL OR NOT EXISTS (
      SELECT 1 FROM pg_class WHERE oid=rel_oid AND relrowsecurity AND relforcerowsecurity
    ) THEN
      RAISE EXCEPTION 'SCOUT_STAGE8_MISSING_RLS_FORCE:%', object_name;
    END IF;
  END LOOP;
  FOR needed_trigger,obj IN
    SELECT * FROM (VALUES
      ('scout_photo_evidence_immutable_guard','scout_photo_evidence'),
      ('scout_photo_grant_mutation_guard','scout_photo_field_access_grants'),
      ('scout_photo_grant_require_audit','scout_photo_field_access_grants'),
      ('scout_photo_admin_audit_immutable','scout_photo_grant_audit_events'),
      ('scout_photo_detection_link_guard','scout_photo_detection_link_events')
    ) AS t(trig,tbl)
  LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_trigger t WHERE t.tgname=needed_trigger
        AND t.tgrelid=to_regclass('public.'||obj) AND t.tgenabled IN ('O','A')
    ) THEN
      RAISE EXCEPTION 'SCOUT_STAGE8_TRIGGER_MISSING_OR_DISABLED:%', needed_trigger;
    END IF;
  END LOOP;
  IF NOT EXISTS (
      SELECT 1 FROM pg_trigger WHERE tgname='scout_photo_grant_require_audit'
        AND tgdeferrable AND tginitdeferred
    ) THEN
      RAISE EXCEPTION 'SCOUT_STAGE8_GRANT_AUDIT_NOT_DEFERRED';
  END IF;
  FOR role_name IN SELECT unnest(ARRAY['sahool_ingest','sahool_app','sahool_jobs','sahool_scout_grant_admin'])
  LOOP
    IF to_regrole(role_name) IS NULL THEN
      RAISE EXCEPTION 'SCOUT_STAGE8_REQUIRED_ROLE_MISSING:%', role_name;
    END IF;
  END LOOP;
  IF EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname IN ('sahool_ingest','sahool_scout_grant_admin')
      AND (rolsuper OR rolbypassrls)
  ) THEN
    RAISE EXCEPTION 'SCOUT_STAGE8_INGEST_OR_ADMIN_BYPASSRLS';
  END IF;
  IF NOT has_column_privilege('sahool_ingest','public.users','role','SELECT') THEN
    RAISE EXCEPTION 'SCOUT_STAGE8_LIVE_ROLE_READ_MISSING';
  END IF;
  IF NOT has_table_privilege('sahool_ingest','public.scout_photo_detection_link_events','INSERT') THEN
    RAISE EXCEPTION 'SCOUT_STAGE8_INGEST_OWNER_WRITE_MISSING';
  END IF;
  IF has_table_privilege('sahool_ingest','public.scout_photo_grant_audit_events','INSERT')
    OR has_table_privilege('sahool_ingest','public.scout_photo_field_access_grants','INSERT') THEN
    RAISE EXCEPTION 'SCOUT_STAGE8_INGEST_ESCALATION';
  END IF;
  FOREACH role_name IN ARRAY ARRAY['sahool_app','sahool_jobs'] LOOP
    FOREACH obj IN ARRAY ARRAY[
      'scout_photo_field_access_grants','scout_photo_grant_audit_events',
      'scout_photo_detection_link_events'
    ] LOOP
      FOREACH kind IN ARRAY ARRAY['INSERT','UPDATE','DELETE'] LOOP
        IF has_table_privilege(role_name, 'public.'||obj, kind) THEN
          RAISE EXCEPTION 'SCOUT_STAGE8_BROAD_DML:%:%:%', role_name,obj,kind;
        END IF;
      END LOOP;
    END LOOP;
  END LOOP;
  IF NOT EXISTS (
     SELECT 1 FROM pg_constraint WHERE conrelid='scout_photo_field_access_grants'::regclass
       AND conname='scout_photo_field_access_grants_scope_check'
       AND pg_get_constraintdef(oid) LIKE '%photo.detection_link%'
  ) THEN
     RAISE EXCEPTION 'SCOUT_STAGE8_SCOPE_CONSTRAINT_MISSING';
  END IF;
END $$;
ROLLBACK;
SELECT 'SCOUT_STAGE8_CATALOG_PASS' AS result;
