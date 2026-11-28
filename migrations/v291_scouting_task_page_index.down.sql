BEGIN;
SET LOCAL lock_timeout = '15s';

DROP STATISTICS IF EXISTS public.st_field_tasks_tenant_text;
DROP INDEX IF EXISTS public.idx_field_tasks_scouting_page;

COMMIT;
