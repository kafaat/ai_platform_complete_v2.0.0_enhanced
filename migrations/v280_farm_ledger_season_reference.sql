-- v280: the farm operations ledger accepts an agronomic season (seasons.season_id) as well as a
-- ledger season project (plan item W1-14, finding business-1).
-- ════════════════════════════════════════════════════════════════════════
-- The fault: every season_id column of the v100-v102 ledger tables was a foreign key to
-- farm_season_projects, a table that no code path writes. The seasons a farmer creates live in
-- `seasons` (v32, written by the platform's seasons router). So an operation, a budget line or a
-- revenue record sent with a real season was refused (the router's tenant check read only
-- farm_season_projects), and had the check passed, the foreign key would have refused the row.
-- The simple farm book (v211) already accepts either table (seasons UNION farm_season_projects)
-- with no foreign key at all.
--
-- This migration replaces each of those foreign keys with one trigger that requires the season
-- to exist, for the row's own tenant, in `seasons` or in `farm_season_projects`. The integrity
-- check stays in the database (a row cannot name an unknown or another tenant's season), and the
-- same two sources the farm book uses are accepted. The trigger is SECURITY INVOKER: it reads both
-- tables under row-level security for the row's own tenant (a write with no tenant context reads
-- with app.current_tenant set to the row's tenant for the lookup, then cleared), so a tenant can
-- only reference its own seasons. A row for another tenant than the context is left to the
-- table's WITH CHECK policy, so the trigger never reveals another tenant's season ids.
-- A violation raises SQLSTATE 23503 (foreign_key_violation), as the foreign key did.
--
-- Not kept: ON DELETE CASCADE / SET NULL from farm_season_projects (which has no writer, so no
-- delete ever reached it). Deleting a season does not delete ledger history.
--
-- Tables (all owned by field-management-service, db_ownership.yml; this is DDL only, no data is
-- written): farm_operation_ledger, farm_season_budget_lines, farm_revenue_records,
-- farm_indirect_cost_pools, farm_ledger_inventory_projections,
-- farm_ledger_erp_projection_outbox, farm_ledger_economic_snapshots.
--
-- Idempotent: foreign keys are found in the catalog and dropped only when present; the function
-- is CREATE OR REPLACE; each trigger is dropped and recreated. Tables missing on a partial schema
-- are skipped.

BEGIN;
SET LOCAL lock_timeout = '15s';

CREATE OR REPLACE FUNCTION farm_ledger_assert_season_ref() RETURNS trigger
    LANGUAGE plpgsql
    SECURITY INVOKER
AS $$
DECLARE
    ctx text := NULLIF(current_setting('app.current_tenant', true), '');
    found boolean;
BEGIN
    IF NEW.season_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF ctx IS NOT NULL AND ctx <> NEW.tenant_id::text THEN
        -- Another tenant's row: the table's own policy (WITH CHECK) refuses it. Answering
        -- here would tell the caller whether that tenant has such a season.
        RETURN NEW;
    END IF;
    IF ctx IS NULL THEN
        -- A write with no tenant context (migration, system job): read under the row's own
        -- tenant, so row-level security applies exactly as for that tenant, then restore.
        PERFORM set_config('app.current_tenant', NEW.tenant_id::text, true);
    END IF;
    found := EXISTS (
        SELECT 1 FROM seasons s
        WHERE s.season_id = NEW.season_id AND s.tenant_id = NEW.tenant_id
    ) OR EXISTS (
        SELECT 1 FROM farm_season_projects p
        WHERE p.season_id = NEW.season_id AND p.tenant_id = NEW.tenant_id
    );
    IF ctx IS NULL THEN
        PERFORM set_config('app.current_tenant', '', true);
    END IF;
    IF found THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'season_not_found_for_tenant: % (table %)', NEW.season_id, TG_TABLE_NAME
        USING ERRCODE = 'foreign_key_violation';
END;
$$;

COMMENT ON FUNCTION farm_ledger_assert_season_ref() IS
    'v280 (W1-14, business-1): a ledger row''s season_id must name a season of the same tenant in '
    'seasons or farm_season_projects. Replaces the v100-v102 foreign keys to farm_season_projects.';

DO $$
DECLARE
    t text;
    c record;
    tables text[] := ARRAY[
        'farm_operation_ledger', 'farm_season_budget_lines', 'farm_revenue_records',
        'farm_indirect_cost_pools', 'farm_ledger_inventory_projections',
        'farm_ledger_erp_projection_outbox', 'farm_ledger_economic_snapshots'
    ];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        IF to_regclass('public.' || t) IS NULL THEN
            CONTINUE;
        END IF;
        FOR c IN
            SELECT con.conname
            FROM pg_constraint con
            JOIN pg_attribute att
              ON att.attrelid = con.conrelid AND att.attnum = ANY (con.conkey)
            WHERE con.contype = 'f'
              AND con.conrelid = ('public.' || t)::regclass
              AND con.confrelid = 'public.farm_season_projects'::regclass
              AND att.attname = 'season_id'
        LOOP
            EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', t, c.conname);
        END LOOP;
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_season_ref ON %I', t, t);
        EXECUTE format(
            'CREATE TRIGGER trg_%s_season_ref BEFORE INSERT OR UPDATE OF season_id, tenant_id '
            'ON %I FOR EACH ROW EXECUTE FUNCTION farm_ledger_assert_season_ref()',
            t, t
        );
    END LOOP;
END $$;

COMMIT;
