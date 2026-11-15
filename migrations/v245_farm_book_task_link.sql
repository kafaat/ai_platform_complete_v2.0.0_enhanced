BEGIN;

-- A nullable link preserves existing unassigned entries and their original digests.
CREATE UNIQUE INDEX IF NOT EXISTS ux_field_tasks_tenant_field_task
    ON field_tasks (tenant_id, field_id, task_id);

ALTER TABLE farm_ledger_entries ADD COLUMN IF NOT EXISTS task_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_farm_book_task_scope'
        AND conrelid = 'farm_ledger_entries'::regclass
    ) THEN
        ALTER TABLE farm_ledger_entries
            ADD CONSTRAINT ck_farm_book_task_field CHECK (task_id IS NULL OR field_id IS NOT NULL),
            ADD CONSTRAINT fk_farm_book_task_scope FOREIGN KEY (tenant_id, field_id, task_id)
                REFERENCES field_tasks (tenant_id, field_id, task_id) ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_farm_book_task_date
    ON farm_ledger_entries (tenant_id, task_id, occurred_on)
    WHERE task_id IS NOT NULL;

COMMIT;
