-- v261 — field_tasks.field_id references the field record (fields), not field_boundaries.
--
-- v9_new_tables pointed field_tasks at field_boundaries because `fields` was then a view
-- ("C2 FIX: FK to TABLE not VIEW"). v9_foundation made `fields` a base table, and it is the
-- record POST /api/v1/fields writes (v134: the draw/PATCH store). field_boundaries is the v8
-- boundary-quality table: nothing in the API inserts into it; the boundary-review routes only
-- UPDATE its quality columns. So a task for a field created through the API failed this FK
-- (an unhandled 500 from the pin-inspection and task imagery/terrain routes). Every later
-- table keyed by a field (v24, v25, v26, v29, v156, v258 ...) already references fields.
--
-- The constraint keeps its name and its ON DELETE CASCADE. Idempotent: the old constraint is
-- found in the catalog by its target table and dropped; the new one is added only if absent.
-- It is added NOT VALID: new and updated rows are checked at once, existing rows are not
-- scanned. Validating it is operator-run, after a clean orphan report, per
-- docs/runbooks/validate_not_valid_constraints.md (no migration runs VALIDATE).
-- edge_results keeps its field_boundaries FK: its writers seed field_boundaries.

DO $$
DECLARE
    old record;
BEGIN
    IF to_regclass('public.field_tasks') IS NULL OR to_regclass('public.fields') IS NULL THEN
        RETURN;
    END IF;
    FOR old IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'public.field_tasks'::regclass AND contype = 'f'
           AND confrelid = to_regclass('public.field_boundaries')
    LOOP
        EXECUTE format('ALTER TABLE field_tasks DROP CONSTRAINT %I', old.conname);
    END LOOP;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.field_tasks'::regclass
           AND conname = 'field_tasks_field_id_fkey'
    ) THEN
        ALTER TABLE field_tasks
            ADD CONSTRAINT field_tasks_field_id_fkey
            FOREIGN KEY (field_id) REFERENCES fields(field_id) ON DELETE CASCADE NOT VALID;
    END IF;
END $$;
