-- v281 rollback: removes the season-reference trigger and restores the foreign keys to
-- farm_season_projects(season_id) on the seven ledger tables.
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
-- Order: roll back the code first (revert W1-14: core/farm_operations_ledger.py
-- _TENANT_SCOPE_SQL['season'] accepts seasons.season_id), then run this script. Idempotent.
-- Data note: rows written after v281 may name a season of the `seasons` table. Each foreign key
-- is added NOT VALID, then validated at once when no row of its table names a season missing
-- from farm_season_projects: the rollback then returns the pre-v281 schema exactly. A table that
-- still holds such rows keeps its key NOT VALID (new writes are checked; a seasons id is refused,
-- as before v281) and the script raises a NOTICE naming it and the row count; run
-- `ALTER TABLE ... VALIDATE CONSTRAINT ...` once those rows are resolved (lab receipt on 0f746db).
BEGIN;
SET LOCAL lock_timeout = '15s';

DO $$
DECLARE
    t text;
    on_delete text;
    orphans bigint;
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
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_season_ref ON %I', t, t);
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = ('public.' || t)::regclass AND conname = t || '_season_id_fkey'
        ) THEN
            -- v100: the operation ledger nulls the season; v101/v102 cascade.
            on_delete := CASE WHEN t = 'farm_operation_ledger' THEN 'SET NULL' ELSE 'CASCADE' END;
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (season_id) '
                'REFERENCES farm_season_projects(season_id) ON DELETE %s NOT VALID',
                t, t || '_season_id_fkey', on_delete
            );
        END IF;
        IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = ('public.' || t)::regclass AND conname = t || '_season_id_fkey'
              AND NOT convalidated
        ) THEN
            EXECUTE format(
                'SELECT count(*) FROM %I x WHERE x.season_id IS NOT NULL AND NOT EXISTS '
                '(SELECT 1 FROM farm_season_projects p WHERE p.season_id = x.season_id)',
                t
            ) INTO orphans;
            IF orphans = 0 THEN
                EXECUTE format('ALTER TABLE %I VALIDATE CONSTRAINT %I', t, t || '_season_id_fkey');
            ELSE
                RAISE NOTICE 'v281 rollback: % keeps % NOT VALID: % row(s) name a season missing '
                    'from farm_season_projects', t, t || '_season_id_fkey', orphans;
            END IF;
        END IF;
    END LOOP;
END $$;

DROP FUNCTION IF EXISTS farm_ledger_assert_season_ref();

COMMIT;
