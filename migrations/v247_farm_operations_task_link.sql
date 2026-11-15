BEGIN;

-- v245 supplies the unique key on field_tasks (tenant_id, field_id, task_id).
ALTER TABLE farm_operation_ledger ADD COLUMN IF NOT EXISTS task_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_farm_operations_task_scope'
        AND conrelid = 'farm_operation_ledger'::regclass
    ) THEN
        ALTER TABLE farm_operation_ledger
            ADD CONSTRAINT ck_farm_operations_task_field CHECK (task_id IS NULL OR field_id IS NOT NULL),
            ADD CONSTRAINT fk_farm_operations_task_scope FOREIGN KEY (tenant_id, field_id, task_id)
                REFERENCES field_tasks (tenant_id, field_id, task_id) ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_farm_operations_task_date
    ON farm_operation_ledger (tenant_id, task_id, operation_date DESC)
    WHERE task_id IS NOT NULL;

COMMIT;
