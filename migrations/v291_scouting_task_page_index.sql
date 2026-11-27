-- Field-management scouting lists use this order, including legacy null dates.
BEGIN;
SET LOCAL lock_timeout = '15s';

CREATE INDEX IF NOT EXISTS idx_field_tasks_scouting_page
    ON public.field_tasks (tenant_id, field_id, created_at DESC NULLS FIRST, task_id ASC)
    WHERE anomaly_ref IS NOT NULL;

-- The tenant isolation policy compares tenant_id::text to a session setting.
-- Give the planner selectivity for that expression when it costs ordered reads.
CREATE STATISTICS IF NOT EXISTS public.st_field_tasks_tenant_text
    ON (tenant_id::text) FROM public.field_tasks;

COMMIT;

-- Release the index build's write lock before sampling an existing table.
ANALYZE public.field_tasks (tenant_id, field_id, season_id, anomaly_ref, created_at, task_id);
