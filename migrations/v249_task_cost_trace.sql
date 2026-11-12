BEGIN;

CREATE TABLE IF NOT EXISTS task_expense_links (
    tenant_id uuid NOT NULL, entry_id text NOT NULL, task_id uuid NOT NULL, field_id varchar(50) NOT NULL,
    linked_by text NOT NULL, linked_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, entry_id),
    FOREIGN KEY (tenant_id, entry_id) REFERENCES farm_ledger_entries(tenant_id, entry_id)
);
-- Upgrade the separately distributed task-cost trace as well as a new installation.
-- Migration runs with the schema administrator. Do not silently skip protected rows.
SET LOCAL row_security = off;
ALTER TABLE task_expense_links ADD COLUMN IF NOT EXISTS field_id varchar(50);
DROP TRIGGER IF EXISTS immutable_record ON task_expense_links;
DO $$
DECLARE
    tenant uuid;
    bad_entry text;
    prior_scope text := current_setting('app.current_tenant', true);
BEGIN
    FOR tenant IN SELECT tenant_id FROM task_expense_links
                  UNION SELECT tenant_id FROM farm_ledger_entries WHERE task_id IS NOT NULL LOOP
        PERFORM set_config('app.current_tenant', tenant::text, true);
        SELECT e.entry_id INTO bad_entry
          FROM farm_ledger_entries e
          LEFT JOIN task_expense_links l ON l.tenant_id=e.tenant_id
               AND l.entry_id=COALESCE(e.settles_entry_id,e.reverses_entry_id,e.entry_id)
          LEFT JOIN field_tasks t ON t.tenant_id=e.tenant_id AND t.task_id=COALESCE(e.task_id,l.task_id)
          LEFT JOIN fields f ON f.tenant_id=t.tenant_id AND f.field_id=t.field_id
         WHERE e.tenant_id=tenant AND COALESCE(e.task_id,l.task_id) IS NOT NULL
           AND (f.farm_id IS DISTINCT FROM e.farm_id OR
                (e.field_id IS NOT NULL AND e.field_id IS DISTINCT FROM t.field_id) OR
                (e.task_id IS NOT NULL AND l.task_id IS NOT NULL AND e.task_id <> l.task_id))
         LIMIT 1;
        IF FOUND THEN
            RAISE EXCEPTION 'v249: conflicting task/farm/field on existing ledger entry % (tenant %)',bad_entry,tenant;
        END IF;
    END LOOP;
    PERFORM set_config('app.current_tenant', COALESCE(prior_scope,''), true);
END $$;
UPDATE task_expense_links l SET field_id=t.field_id FROM field_tasks t
 WHERE l.field_id IS NULL AND l.tenant_id=t.tenant_id AND l.task_id=t.task_id;
ALTER TABLE task_expense_links ALTER COLUMN field_id SET NOT NULL;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='task_expense_links'::regclass
                   AND conname='fk_task_expense_link_scope') THEN
        ALTER TABLE task_expense_links ADD CONSTRAINT fk_task_expense_link_scope
            FOREIGN KEY (tenant_id, field_id, task_id)
            REFERENCES field_tasks(tenant_id, field_id, task_id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_task_expense_links ON task_expense_links(tenant_id, task_id);
CREATE TABLE IF NOT EXISTS task_cost_history (
    change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL, task_id uuid NOT NULL, changed_at timestamptz NOT NULL DEFAULT now(),
    changed_by text, previous_usd numeric, actual_usd numeric, previous_status text, status text
);
CREATE INDEX IF NOT EXISTS ix_task_cost_history ON task_cost_history(tenant_id,task_id,change_id);
DO $$ DECLARE tbl text; BEGIN
    FOREACH tbl IN ARRAY ARRAY['task_expense_links','task_cost_history'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',tbl);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',tbl);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I',tbl);
        EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id::text = current_setting(''app.current_tenant'',true)) WITH CHECK (tenant_id::text = current_setting(''app.current_tenant'',true))',tbl);
        EXECUTE format('DROP TRIGGER IF EXISTS immutable_record ON %I',tbl);
        EXECUTE format('CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION sahool_simple_farm_book_immutable()',tbl);
    END LOOP;
END $$;
CREATE OR REPLACE FUNCTION record_field_task_cost() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.tenant_id IS NOT NULL AND (
        NEW.actual_cost_usd IS DISTINCT FROM OLD.actual_cost_usd OR
        (NEW.actual_cost_usd IS NOT NULL AND NEW.status IS DISTINCT FROM OLD.status)
    ) THEN
        INSERT INTO task_cost_history(tenant_id,task_id,changed_by,previous_usd,actual_usd,previous_status,status)
        VALUES(NEW.tenant_id,NEW.task_id,nullif(current_setting('app.current_user_id',true),''),
               OLD.actual_cost_usd,NEW.actual_cost_usd,OLD.status,NEW.status);
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS record_field_task_cost ON field_tasks;
CREATE TRIGGER record_field_task_cost AFTER INSERT OR UPDATE ON field_tasks
FOR EACH ROW EXECUTE FUNCTION record_field_task_cost();
COMMIT;
