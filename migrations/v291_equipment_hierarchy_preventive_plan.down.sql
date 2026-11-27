-- v291 rollback: drops the hierarchy and preventive-plan columns. Recorded parent links,
-- intervals and service meter readings are lost.
BEGIN;
SET LOCAL lock_timeout = '15s';
DROP TRIGGER IF EXISTS trg_equipment_parent_guard ON public.equipment;
DROP FUNCTION IF EXISTS public.equipment_parent_guard();
DROP INDEX IF EXISTS public.idx_equipment_parent;
ALTER TABLE public.equipment
    DROP CONSTRAINT IF EXISTS equipment_service_interval_positive,
    DROP CONSTRAINT IF EXISTS equipment_last_service_nonneg,
    DROP CONSTRAINT IF EXISTS equipment_not_own_parent,
    DROP COLUMN IF EXISTS parent_equipment_id,
    DROP COLUMN IF EXISTS service_interval_hours,
    DROP COLUMN IF EXISTS last_service_hours;
ALTER TABLE public.equipment_maintenance
    DROP CONSTRAINT IF EXISTS equipment_maintenance_meter_nonneg,
    DROP COLUMN IF EXISTS meter_hours;
COMMIT;
