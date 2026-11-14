-- Phase11: PostgreSQL staging-only catalog proof; strictly READ ONLY.
-- This does not prove live tenant RLS (use stage10 gate), actual MinIO, or Flutter.
\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL statement_timeout='15s';
DO $scout_stage11$
DECLARE obj TEXT; tab TEXT; trig TEXT; role TEXT; privilege TEXT;
BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'SCOUT_STAGE11_PG15_REQUIRED';
  END IF;
  FOREACH tab IN ARRAY ARRAY[
    'scout_plant_tissue_samples','scout_tissue_custody_events',
    'scout_specialist_credential_events','scout_treatment_review_events',
    'scout_photo_retention_policy_events','scout_photo_retention_events'
  ] LOOP
    IF to_regclass('public.'||tab) IS NULL OR NOT EXISTS(
      SELECT 1 FROM pg_class c WHERE c.oid=to_regclass('public.'||tab)
        AND c.relrowsecurity AND c.relforcerowsecurity
    ) THEN
      RAISE EXCEPTION 'SCOUT_STAGE11_RLS_FORCE_MISSING:%',tab;
    END IF;
  END LOOP;
  FOR trig,tab IN SELECT * FROM (VALUES
    ('scout_tissue_sample_guard','scout_plant_tissue_samples'),
    ('scout_tissue_custody_guard','scout_tissue_custody_events'),
    ('scout_tissue_deferred_collection_guard','scout_plant_tissue_samples'),
    ('scout_credentials_event_guard','scout_specialist_credential_events'),
    ('scout_review_credential_required','scout_photo_human_review_events'),
    ('scout_treatment_review_guard','scout_treatment_review_events'),
    ('scout_retention_policy_guard','scout_photo_retention_policy_events'),
    ('scout_retention_event_guard','scout_photo_retention_events')
  ) AS t(trig,tbl) LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_trigger t WHERE t.tgname=trig
        AND t.tgrelid=to_regclass('public.'||tab) AND t.tgenabled IN ('O','A')) THEN
      RAISE EXCEPTION 'SCOUT_STAGE11_TRIGGER_MISSING:%',trig;
    END IF;
  END LOOP;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='scout_tissue_deferred_collection_guard'
      AND tgdeferrable AND tginitdeferred) THEN
    RAISE EXCEPTION 'SCOUT_STAGE11_DEFERRABLE_COLLECTION_NOT_ENFORCED';
  END IF;
  FOR obj,tab IN SELECT * FROM (VALUES
    ('scout_tissue_photo_fk','scout_plant_tissue_samples'),
    ('scout_tissue_custody_sample_fk','scout_tissue_custody_events'),
    ('scout_treatment_human_review_fk','scout_treatment_review_events'),
    ('scout_retention_photo_fk','scout_photo_retention_events'),
    ('scout_credentials_subject_fk','scout_specialist_credential_events')
  ) AS t(c,tbl) LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conname=obj
        AND k.conrelid=to_regclass('public.'||tab) AND k.contype='f' AND k.convalidated) THEN
      RAISE EXCEPTION 'SCOUT_STAGE11_COMPOSITE_FK_MISSING:%',obj;
    END IF;
  END LOOP;
  -- Ingest can append tissue/custody/treatment, not owner-only credentials/holds.
  FOREACH tab IN ARRAY ARRAY['scout_plant_tissue_samples',
          'scout_tissue_custody_events','scout_treatment_review_events'] LOOP
    IF NOT has_table_privilege('sahool_ingest','public.'||tab,'SELECT') OR
       NOT has_table_privilege('sahool_ingest','public.'||tab,'INSERT') THEN
      RAISE EXCEPTION 'SCOUT_STAGE11_INGEST_MISSING_APPEND:%',tab;
    END IF;
  END LOOP;
  FOREACH tab IN ARRAY ARRAY['scout_specialist_credential_events',
          'scout_photo_retention_policy_events','scout_photo_retention_events'] LOOP
    IF NOT has_table_privilege('sahool_ingest','public.'||tab,'SELECT') OR
       has_table_privilege('sahool_ingest','public.'||tab,'INSERT') THEN
      RAISE EXCEPTION 'SCOUT_STAGE11_OWNER_LEDGER_INGEST_WRITE:%',tab;
    END IF;
    IF NOT has_table_privilege('sahool_scout_grant_admin','public.'||tab,'INSERT') THEN
      RAISE EXCEPTION 'SCOUT_STAGE11_OWNER_ADMIN_MISSING_APPEND:%',tab;
    END IF;
  END LOOP;
  -- No operational role may UPDATE/DELETE append-only histories, even via broad grants.
  FOREACH role IN ARRAY ARRAY['sahool_ingest','sahool_app','sahool_jobs',
      'sahool_scout_grant_admin'] LOOP
    FOREACH tab IN ARRAY ARRAY['scout_plant_tissue_samples','scout_tissue_custody_events',
      'scout_specialist_credential_events','scout_treatment_review_events',
      'scout_photo_retention_policy_events','scout_photo_retention_events'] LOOP
      FOREACH privilege IN ARRAY ARRAY['UPDATE','DELETE','TRUNCATE'] LOOP
        IF has_table_privilege(role,'public.'||tab,privilege) THEN
          RAISE EXCEPTION 'SCOUT_STAGE11_ILLEGAL_ROLE_WRITE:%:%:%',role,tab,privilege;
        END IF;
      END LOOP;
      IF role IN ('sahool_app','sahool_jobs') AND
          has_table_privilege(role,'public.'||tab,'INSERT') THEN
        RAISE EXCEPTION 'SCOUT_STAGE11_GENERIC_ROLE_APPEND:%:%',role,tab;
      END IF;
    END LOOP;
  END LOOP;
END $scout_stage11$;
ROLLBACK;
SELECT 'SCOUT_STAGE11_CATALOG_STAGING_READ_ONLY_PASS' AS result;
