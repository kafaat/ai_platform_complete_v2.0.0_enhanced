-- v276: a task's cost trace, owned by field-management-service.
-- ════════════════════════════════════════════════════════════════════════
-- Rebuilds the held v249 (carrier D #1439) on main, as new tables:
--   task_expense_links — links an existing farm-book expense (farm_ledger_entries, v211, written
--     before v245 gave entries a task_id) to a task. Append-only, one link per entry. The link
--     guard refuses an entry that is not an original expense, whose farm is not the task's field's
--     farm, whose field (when it names one) is not the task's field, or that already names another
--     task. The farm book applies the link to the entry and to its settlements and corrections.
--   task_cost_history — one row each time field_tasks.actual_cost_usd changes, or the status of a
--     task that has an actual cost changes, written by the record_field_task_cost trigger whoever
--     updates the task (changed_by = app.current_user_id). Append-only.
-- Both FORCE RLS by tenant. Idempotent on a re-applied MANIFEST.
BEGIN;
CREATE TABLE IF NOT EXISTS task_expense_links (
    tenant_id uuid NOT NULL,
    entry_id text NOT NULL,
    task_id uuid NOT NULL,
    field_id varchar(50) NOT NULL,
    linked_by text NOT NULL CHECK (length(btrim(linked_by)) > 0),
    linked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, entry_id),
    CONSTRAINT task_expense_link_entry_fk FOREIGN KEY (tenant_id, entry_id)
        REFERENCES farm_ledger_entries (tenant_id, entry_id) ON DELETE RESTRICT,
    CONSTRAINT task_expense_link_task_fk FOREIGN KEY (tenant_id, field_id, task_id)
        REFERENCES field_tasks (tenant_id, field_id, task_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_task_expense_links_task ON task_expense_links (tenant_id, task_id);

CREATE TABLE IF NOT EXISTS task_cost_history (
    change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL,
    task_id uuid NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    changed_by text,
    previous_usd numeric(10, 2),
    actual_usd numeric(10, 2),
    previous_status text,
    status text
);
CREATE INDEX IF NOT EXISTS ix_task_cost_history_task ON task_cost_history (tenant_id, task_id, change_id);

DO $$
DECLARE tbl text;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['task_expense_links', 'task_cost_history'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', tbl);
        EXECUTE format('DROP POLICY IF EXISTS tenant_read ON %I', tbl);
        EXECUTE format('CREATE POLICY tenant_read ON %I FOR SELECT USING '
            '(tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))', tbl);
        EXECUTE format('DROP POLICY IF EXISTS tenant_append ON %I', tbl);
        EXECUTE format('CREATE POLICY tenant_append ON %I FOR INSERT WITH CHECK '
            '(tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))', tbl);
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', tbl || '_append_only', tbl);
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW '
            'EXECUTE FUNCTION field_mgmt_append_only()', tbl || '_append_only', tbl);
    END LOOP;
END $$;

CREATE OR REPLACE FUNCTION task_expense_link_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    entry record;
    task_farm text;
BEGIN
    SELECT entry_type, reverses_entry_id, settles_entry_id, farm_id, field_id, task_id INTO entry
      FROM farm_ledger_entries WHERE tenant_id = NEW.tenant_id AND entry_id = NEW.entry_id;
    IF NOT FOUND OR entry.entry_type <> 'expense' OR entry.reverses_entry_id IS NOT NULL
       OR entry.settles_entry_id IS NOT NULL THEN
        RAISE EXCEPTION 'original_expense_required' USING ERRCODE = '23514';
    END IF;
    SELECT f.farm_id INTO task_farm FROM fields f
     WHERE f.tenant_id = NEW.tenant_id AND f.field_id = NEW.field_id;
    IF task_farm IS NULL OR entry.farm_id IS DISTINCT FROM task_farm THEN
        RAISE EXCEPTION 'task_farm_mismatch' USING ERRCODE = '23514';
    END IF;
    IF entry.field_id IS NOT NULL AND entry.field_id <> NEW.field_id THEN
        RAISE EXCEPTION 'task_field_mismatch' USING ERRCODE = '23514';
    END IF;
    IF entry.task_id IS NOT NULL AND entry.task_id <> NEW.task_id THEN
        RAISE EXCEPTION 'entry_already_linked' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS task_expense_link_guard ON task_expense_links;
CREATE TRIGGER task_expense_link_guard BEFORE INSERT ON task_expense_links
    FOR EACH ROW EXECUTE FUNCTION task_expense_link_guard();

CREATE OR REPLACE FUNCTION record_field_task_cost() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.tenant_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.actual_cost_usd IS NULL THEN
            RETURN NEW;
        END IF;
    ELSIF NEW.actual_cost_usd IS NOT DISTINCT FROM OLD.actual_cost_usd
          AND (NEW.actual_cost_usd IS NULL OR NEW.status IS NOT DISTINCT FROM OLD.status) THEN
        RETURN NEW;
    END IF;
    INSERT INTO task_cost_history
        (tenant_id, task_id, changed_by, previous_usd, actual_usd, previous_status, status)
    VALUES (NEW.tenant_id, NEW.task_id, NULLIF(current_setting('app.current_user_id', true), ''),
            CASE WHEN TG_OP = 'UPDATE' THEN OLD.actual_cost_usd END, NEW.actual_cost_usd,
            CASE WHEN TG_OP = 'UPDATE' THEN OLD.status END, NEW.status);
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS record_field_task_cost ON field_tasks;
CREATE TRIGGER record_field_task_cost AFTER INSERT OR UPDATE ON field_tasks
    FOR EACH ROW EXECUTE FUNCTION record_field_task_cost();

COMMENT ON TABLE task_expense_links IS
    'Append-only links from an original farm-book expense to a task (v276, owner field-management-service).';
COMMENT ON TABLE task_cost_history IS
    'Append-only history of field_tasks.actual_cost_usd, written by the record_field_task_cost trigger (v276, owner field-management-service).';
COMMIT;
