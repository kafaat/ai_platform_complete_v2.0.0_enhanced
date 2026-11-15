-- Staging-only PostgreSQL 15+ read-only catalog gate for photo lab and human links.
-- A passing catalog check is NOT live tenant isolation, S3 or Flutter acceptance.
\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL statement_timeout='15s';
DO $$
DECLARE table_name text;
        trigger_name text;
        obj text;
        role_name text;
        kind text;
BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'SCOUT_STAGE9_PG15_REQUIRED';
  END IF;
  FOREACH table_name IN ARRAY ARRAY[
    'scout_photo_lab_link_events','scout_photo_human_review_events','lab_samples'
  ] LOOP
    IF to_regclass('public.'||table_name) IS NULL OR NOT EXISTS (
      SELECT 1 FROM pg_class c WHERE c.oid=to_regclass('public.'||table_name)
        AND c.relrowsecurity AND c.relforcerowsecurity
    ) THEN
      RAISE EXCEPTION 'SCOUT_STAGE9_RLS_FORCE_MISSING:%',table_name;
    END IF;
  END LOOP;
  FOR trigger_name,obj IN SELECT * FROM (VALUES
    ('scout_photo_lab_link_guard','scout_photo_lab_link_events'),
    ('scout_photo_human_review_guard','scout_photo_human_review_events')
  ) t(trig,tbl) LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_trigger t WHERE t.tgname=trigger_name
        AND t.tgrelid=to_regclass('public.'||obj) AND t.tgenabled IN ('O','A')
    ) THEN
      RAISE EXCEPTION 'SCOUT_STAGE9_TRIGGER_MISSING:%',trigger_name;
    END IF;
  END LOOP;
  FOR obj,table_name IN SELECT * FROM (VALUES
    ('scout_photo_lab_photo_fk','scout_photo_lab_link_events'),
    ('scout_photo_lab_sample_fk','scout_photo_lab_link_events'),
    ('scout_photo_lab_prev_fk','scout_photo_lab_link_events'),
    ('scout_photo_human_photo_fk','scout_photo_human_review_events'),
    ('scout_photo_human_actor_fk','scout_photo_human_review_events'),
    ('scout_photo_human_prev_fk','scout_photo_human_review_events')
  ) AS t(c,tbl) LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint k WHERE k.conname=obj AND k.contype='f'
        AND k.conrelid=to_regclass('public.'||table_name)
        AND k.convalidated
    ) THEN
      RAISE EXCEPTION 'SCOUT_STAGE9_COMPOSITE_FK_MISSING:%',obj;
    END IF;
  END LOOP;
  IF NOT has_column_privilege('sahool_ingest','public.lab_samples','kind','SELECT')
     OR NOT has_column_privilege('sahool_ingest','public.lab_samples','status','SELECT')
     OR NOT has_table_privilege('sahool_ingest','public.scout_photo_lab_link_events','INSERT')
     OR NOT has_table_privilege('sahool_ingest','public.scout_photo_human_review_events','INSERT')
  THEN
    RAISE EXCEPTION 'SCOUT_STAGE9_INGEST_REQUIRED_PRIVILEGE_MISSING';
  END IF;
  FOREACH role_name IN ARRAY ARRAY['sahool_app','sahool_jobs','sahool_scout_grant_admin'] LOOP
    FOREACH obj IN ARRAY ARRAY['scout_photo_lab_link_events','scout_photo_human_review_events'] LOOP
      FOREACH kind IN ARRAY ARRAY['SELECT','INSERT','UPDATE','DELETE'] LOOP
        IF has_table_privilege(role_name,'public.'||obj,kind) THEN
          RAISE EXCEPTION 'SCOUT_STAGE9_BROAD_DML:%:%:%',role_name,obj,kind;
        END IF;
      END LOOP;
    END LOOP;
  END LOOP;
  FOREACH obj IN ARRAY ARRAY['scout_photo_lab_link_events','scout_photo_human_review_events'] LOOP
    FOREACH kind IN ARRAY ARRAY['UPDATE','DELETE'] LOOP
      IF has_table_privilege('sahool_ingest','public.'||obj,kind) THEN
        RAISE EXCEPTION 'SCOUT_STAGE9_INGEST_MUTATION:%:%',obj,kind;
      END IF;
    END LOOP;
  END LOOP;
  FOR obj IN SELECT unnest(ARRAY[
    'scout_photo_field_access_grants','scout_photo_grant_audit_events'
  ]) LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint k WHERE k.conrelid=to_regclass('public.'||obj)
        AND k.contype='c' AND pg_get_constraintdef(k.oid) LIKE '%photo.lab_link%'
        AND pg_get_constraintdef(k.oid) LIKE '%photo.diagnosis_review%'
    ) THEN
      RAISE EXCEPTION 'SCOUT_STAGE9_SCOPE_MISSING:%',obj;
    END IF;
  END LOOP;
END $$;
ROLLBACK;
SELECT 'SCOUT_STAGE9_CATALOG_PASS' AS result;
