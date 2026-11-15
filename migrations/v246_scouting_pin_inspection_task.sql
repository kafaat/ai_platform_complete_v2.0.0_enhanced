-- One initial inspection per saved scouting pin. Other work on the field remains independent.
BEGIN;
CREATE UNIQUE INDEX IF NOT EXISTS scouting_pins_tenant_field_pin_uq
    ON scouting_pins (tenant_id, field_id, pin_id);

ALTER TABLE field_tasks
    ADD COLUMN IF NOT EXISTS source_scouting_pin_id text,
    ADD COLUMN IF NOT EXISTS inspection_due_at timestamptz,
    ADD COLUMN IF NOT EXISTS inspection_assigned_by text,
    ADD COLUMN IF NOT EXISTS inspection_initial_assignee text;

-- MATCH SIMPLE preserves legacy tasks without pins. A sourced task must have a tenant.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'field_tasks'::regclass AND conname = 'field_task_pin_scope_fk') THEN
        ALTER TABLE field_tasks ADD CONSTRAINT field_task_pin_scope_fk
            FOREIGN KEY (tenant_id, field_id, source_scouting_pin_id)
            REFERENCES scouting_pins (tenant_id, field_id, pin_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'field_tasks'::regclass AND conname = 'field_task_pin_tenant_ck') THEN
        ALTER TABLE field_tasks ADD CONSTRAINT field_task_pin_tenant_ck
            CHECK (source_scouting_pin_id IS NULL OR tenant_id IS NOT NULL);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS field_tasks_inspection_pin_uq
    ON field_tasks (source_scouting_pin_id) WHERE source_scouting_pin_id IS NOT NULL;
COMMIT;
