-- v291: asset hierarchy and recorded preventive-maintenance policy on the existing equipment tables.
-- Extends v23 only. No predictive field is added: a plan is a recorded interval and a meter
-- reading taken at a real service, never an estimate.
BEGIN;
SET LOCAL lock_timeout = '15s';

ALTER TABLE public.equipment
    ADD COLUMN IF NOT EXISTS parent_equipment_id VARCHAR(50)
        REFERENCES public.equipment(equipment_id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS service_interval_hours NUMERIC(12, 1),
    ADD COLUMN IF NOT EXISTS last_service_hours NUMERIC(12, 1);

ALTER TABLE public.equipment
    DROP CONSTRAINT IF EXISTS equipment_service_interval_positive,
    ADD CONSTRAINT equipment_service_interval_positive
        CHECK (service_interval_hours IS NULL OR service_interval_hours > 0),
    DROP CONSTRAINT IF EXISTS equipment_last_service_nonneg,
    ADD CONSTRAINT equipment_last_service_nonneg
        CHECK (last_service_hours IS NULL OR last_service_hours >= 0),
    DROP CONSTRAINT IF EXISTS equipment_not_own_parent,
    ADD CONSTRAINT equipment_not_own_parent
        CHECK (parent_equipment_id IS NULL OR parent_equipment_id <> equipment_id);

ALTER TABLE public.equipment_maintenance
    ADD COLUMN IF NOT EXISTS meter_hours NUMERIC(12, 1);
ALTER TABLE public.equipment_maintenance
    DROP CONSTRAINT IF EXISTS equipment_maintenance_meter_nonneg,
    ADD CONSTRAINT equipment_maintenance_meter_nonneg
        CHECK (meter_hours IS NULL OR meter_hours >= 0);

CREATE INDEX IF NOT EXISTS idx_equipment_parent
    ON public.equipment(tenant_id, parent_equipment_id) WHERE parent_equipment_id IS NOT NULL;

-- A parent must belong to the same tenant and the chain must not loop. The lookup runs as the
-- caller, so under row-level security another tenant's asset is simply not found.
CREATE OR REPLACE FUNCTION public.equipment_parent_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    cursor_id VARCHAR(50);
    hops INT := 0;
BEGIN
    IF NEW.parent_equipment_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.equipment p
                   WHERE p.equipment_id = NEW.parent_equipment_id AND p.tenant_id = NEW.tenant_id) THEN
        RAISE EXCEPTION 'equipment_parent_not_in_tenant' USING ERRCODE = '23514';
    END IF;
    cursor_id := NEW.parent_equipment_id;
    WHILE cursor_id IS NOT NULL LOOP
        IF cursor_id = NEW.equipment_id THEN
            RAISE EXCEPTION 'equipment_parent_cycle' USING ERRCODE = '23514';
        END IF;
        hops := hops + 1;
        IF hops > 32 THEN
            RAISE EXCEPTION 'equipment_hierarchy_too_deep' USING ERRCODE = '23514';
        END IF;
        SELECT p.parent_equipment_id INTO cursor_id FROM public.equipment p
         WHERE p.equipment_id = cursor_id AND p.tenant_id = NEW.tenant_id;
    END LOOP;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_equipment_parent_guard ON public.equipment;
CREATE TRIGGER trg_equipment_parent_guard
    BEFORE INSERT OR UPDATE OF parent_equipment_id, tenant_id ON public.equipment
    FOR EACH ROW EXECUTE FUNCTION public.equipment_parent_guard();

COMMENT ON COLUMN public.equipment.parent_equipment_id IS
    'Optional parent asset in the same tenant (e.g. a pump under a pump station). v291.';
COMMENT ON COLUMN public.equipment.service_interval_hours IS
    'Recorded preventive-service interval in meter hours; NULL means no policy. v291.';
COMMENT ON COLUMN public.equipment.last_service_hours IS
    'Meter reading recorded at the last completed scheduled service; NULL means unknown. v291.';

COMMIT;
