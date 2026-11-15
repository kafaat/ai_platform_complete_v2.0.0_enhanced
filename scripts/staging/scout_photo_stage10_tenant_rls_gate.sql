-- PHASE10: READ-ONLY live staging canary for two pre-seeded tenants.
-- This proves the actual restricted ingest role sees its tenant and not the other.
-- Does not create fixtures, change grants, simulate MinIO, or approve deployment.
\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL statement_timeout='15s';
SET LOCAL ROLE sahool_ingest;
SELECT set_config('app.current_tenant', :'fixture_tenant_a', true);
DO $scout_stage10_a$
DECLARE this_tenant uuid := current_setting('app.current_tenant',true)::uuid;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.scout_photo_evidence WHERE tenant_id=this_tenant) THEN
    RAISE EXCEPTION 'SCOUT_STAGE10_TENANT_A_POSITIVE_FIXTURE_MISSING';
  END IF;
  IF EXISTS (SELECT 1 FROM public.scout_photo_evidence WHERE tenant_id<>this_tenant) THEN
    RAISE EXCEPTION 'SCOUT_STAGE10_CROSS_TENANT_READ_A';
  END IF;
END $scout_stage10_a$;
SELECT set_config('app.current_tenant', :'fixture_tenant_b', true);
DO $scout_stage10_b$
DECLARE this_tenant uuid := current_setting('app.current_tenant',true)::uuid;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.scout_photo_evidence WHERE tenant_id=this_tenant) THEN
    RAISE EXCEPTION 'SCOUT_STAGE10_TENANT_B_POSITIVE_FIXTURE_MISSING';
  END IF;
  IF EXISTS (SELECT 1 FROM public.scout_photo_evidence WHERE tenant_id<>this_tenant) THEN
    RAISE EXCEPTION 'SCOUT_STAGE10_CROSS_TENANT_READ_B';
  END IF;
END $scout_stage10_b$;
-- Missing tenant context is fail-closed, including for a privileged table owner.
SELECT set_config('app.current_tenant', '', true);
DO $scout_stage10_none$
BEGIN
  IF EXISTS (SELECT 1 FROM public.scout_photo_evidence) THEN
    RAISE EXCEPTION 'SCOUT_STAGE10_MISSING_TENANT_READABLE';
  END IF;
END $scout_stage10_none$;
ROLLBACK;
SELECT 'SCOUT_STAGE10_RLS_STAGING_READ_ONLY_PASS' AS result;
