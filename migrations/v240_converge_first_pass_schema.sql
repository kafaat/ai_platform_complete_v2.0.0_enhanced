-- v240_converge_first_pass_schema.sql — مرورٌ واحد على MANIFEST == مروران (لا اعتماد على المسار).
--
-- المقيس (PG 16، قاعدة فارغة، c966fd0b2): تطبيق MANIFEST مرّةً ثمّ مرّتين يُعطي مخطّطَين مختلفين
-- في 55 سطراً من `pg_dump -s -x -O` المُطبَّع. والمُهاجر يُعيد MANIFEST كاملاً في كلّ تشغيل،
-- فالإنتاج في حالة «مرّتين» والتثبيت الجديد في حالة «مرّة» — مخطّطان لمنتجٍ واحد.
--
-- السبب: كائناتٌ تُنشأ **مشروطةً** بوجود جدولٍ لا يُنشأ إلّا في هجرةٍ **لاحقة**، فتظهر في المرور
-- الثاني فقط:
--
--   المُنشِئ (موضعه في MANIFEST)        الجدول يُنشأ في (موضعه)                  الكائن
--   ─────────────────────────────────   ──────────────────────────────────────   ───────────────────────────────
--   v9_foundation (2)                    v9_new_tables (4)                        idx_edge_results_brin
--                                                                                 chk_confidence_range (agent_queries)
--                                                                                 chk_risk_levels (guardrails_log)
--                                                                                 idx_ft_source_event
--                                                                                 idx_workflow_expires
--   v9_new_tables (4)                    v9_market (6)                            idx_market_listings_crop_status
--                                                                                 idx_market_listings_tenant_status
--   v57_rls_dynamic_indexes (63)         v100…v231 (106…229)                      idx_<t>_tenant لـ46 جدولاً أدناه
--
-- (والفرق السادس «موضع created_at» ليس كائناً: هو فاصلةٌ تتبع آخر عمود حين يُلحَق CHECK بالجدول.)
--
-- الإصلاح هنا لا في الهجرات القديمة: يُنشئ **تلك الكائنات بعينها** بالتعريف نفسه الذي يُنشئها به
-- المرور الثاني، وبالشرط نفسه، فيصير المرور الأوّل مساوياً للثاني. وعلى قاعدةٍ في حالة «مرّتين»
-- (الإنتاج) كلّ فرعٍ هنا no-op: يُفحص الكتالوج **قبل** أيّ DDL فلا يُؤخذ قفلٌ على جدولٍ قائم الفهرس.
--
-- يُدرَج مباشرةً قبل v206 (الذي يبقى آخِراً). هجرةٌ جديدة تُنشئ جدولاً tenant بلا فهرس tenant_id
-- وتُدرَج **بعد** هذا الملف تُعيد الصنف؛ الاختبار الحيّ tests_v9/test_v240_first_pass_convergence_live_pg.py
-- يقيس مرّةً == مرّتين ويحمرّ عندها.

BEGIN;
SET LOCAL lock_timeout = '15s';

-- ── (1) مُؤجَّلات v9_foundation: جداولها من v9_new_tables ──────────────────────────────────
DO $$
BEGIN
    IF to_regclass('public.edge_results') IS NOT NULL
       AND to_regclass('public.idx_edge_results_brin') IS NULL THEN
        CREATE INDEX IF NOT EXISTS idx_edge_results_brin ON edge_results USING BRIN (recorded_at);
    END IF;

    IF to_regclass('public.agent_queries') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_confidence_range') THEN
        ALTER TABLE agent_queries
            ADD CONSTRAINT chk_confidence_range
            CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1);
    END IF;

    IF to_regclass('public.guardrails_log') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_risk_levels') THEN
        ALTER TABLE guardrails_log
            ADD CONSTRAINT chk_risk_levels
            CHECK (overall_risk IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'));
    END IF;

    IF to_regclass('public.field_tasks') IS NOT NULL
       AND to_regclass('public.idx_ft_source_event') IS NULL THEN
        CREATE INDEX IF NOT EXISTS idx_ft_source_event ON field_tasks (source_event_type);
    END IF;

    IF to_regclass('public.approval_workflows') IS NOT NULL
       AND to_regclass('public.idx_workflow_expires') IS NULL THEN
        CREATE INDEX IF NOT EXISTS idx_workflow_expires ON approval_workflows (expires_at);
    END IF;
END $$;

-- ── (2) مُؤجَّلات v9_new_tables: market_sales_listings من v9_market ────────────────────────
DO $$
BEGIN
    IF to_regclass('public.market_sales_listings') IS NOT NULL THEN
        IF to_regclass('public.idx_market_listings_crop_status') IS NULL THEN
            CREATE INDEX IF NOT EXISTS idx_market_listings_crop_status
                ON market_sales_listings (crop_type, status);
        END IF;
        IF to_regclass('public.idx_market_listings_tenant_status') IS NULL THEN
            CREATE INDEX IF NOT EXISTS idx_market_listings_tenant_status
                ON market_sales_listings (tenant_id, status);
        END IF;
    END IF;
END $$;

-- ── (3) مُؤجَّلات v57: جداول tenant أُنشئت بعده ────────────────────────────────────────────
-- الشرط حرفُ شرط v57: لا يُنشأ idx_<t>_tenant إن كان للجدول أصلاً فهرسٌ صدارته tenant_id.
DO $$
DECLARE
    t text;
    n int := 0;
    tables text[] := ARRAY[
        'actuator_command_outbox', 'agent_proposals', 'autonomous_execution_plan',
        'digital_twin_scenarios', 'execution_verification_event', 'external_ingest_sources',
        'farm_energy_records', 'farm_equipment_records', 'farm_labor_records',
        'farm_production_units', 'farm_season_projects', 'federated_policy_experiments',
        'field_feature_store_candidate', 'gis_collaboration_events',
        'irrigation_battery_systems', 'irrigation_energy_loads', 'irrigation_generators',
        'irrigation_grid_connections', 'irrigation_hybrid_inverters',
        'irrigation_hydraulic_nodes', 'irrigation_pv_arrays', 'irrigation_runs',
        'irrigation_sprinkler_packages', 'irrigation_sprinkler_zones',
        'irrigation_water_samples', 'market_procurement_items', 'market_suppliers',
        'marketplace_plugin_output_validations', 'mfa_audit_events', 'mfa_recovery_codes',
        'model_experiment_assignment', 'ogc_conformance_runs', 'outbox_delivery_attempts',
        'plugin_permission_audit', 'runtime_event_outbox', 'season_cost_items', 'season_crop',
        'season_events', 'season_harvest', 'soil_learning_attributions', 'soil_outcome_records',
        'soil_reconciliation_checkpoints', 'soil_reconciliation_deferrals',
        'soil_verification_records', 'webhook_deliveries', 'yield_stability_maps'
    ];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        CONTINUE WHEN to_regclass(format('public.%I', t)) IS NULL;
        CONTINUE WHEN NOT EXISTS (
            SELECT 1 FROM information_schema.columns c
            WHERE c.table_schema = 'public' AND c.table_name = t AND c.column_name = 'tenant_id');
        CONTINUE WHEN EXISTS (
            SELECT 1
            FROM pg_index ix
            JOIN pg_class ic ON ic.oid = ix.indrelid
            JOIN pg_namespace ns ON ns.oid = ic.relnamespace
            JOIN pg_attribute a ON a.attrelid = ix.indrelid AND a.attnum = ix.indkey[0]
            WHERE ns.nspname = 'public' AND ic.relname = t AND a.attname = 'tenant_id');
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (tenant_id)', 'idx_' || t || '_tenant', t);
        n := n + 1;
    END LOOP;
    RAISE NOTICE 'v240: tenant_id indexes converged = %', n;
END $$;

-- ── (4) تحذيرٌ لا حجب: ما سيُنشئه v57 في مرورٍ ثانٍ ولم يُنشأ بعد ⇒ اعتمادُ مسارٍ جديد ────────────
DO $$
DECLARE
    pending text;
BEGIN
    SELECT string_agg(t.tablename, ', ' ORDER BY t.tablename) INTO pending
    FROM pg_tables t
    WHERE t.schemaname = 'public'
      AND EXISTS (SELECT 1 FROM information_schema.columns c
                  WHERE c.table_schema = 'public' AND c.table_name = t.tablename
                    AND c.column_name = 'tenant_id')
      AND NOT EXISTS (
          SELECT 1
          FROM pg_index ix
          JOIN pg_class ic ON ic.oid = ix.indrelid
          JOIN pg_namespace ns ON ns.oid = ic.relnamespace
          JOIN pg_attribute a ON a.attrelid = ix.indrelid AND a.attnum = ix.indkey[0]
          WHERE ns.nspname = 'public' AND ic.relname = t.tablename AND a.attname = 'tenant_id');
    IF pending IS NOT NULL THEN
        RAISE WARNING 'v240: v57 would still create idx_<t>_tenant on a second pass (schema path-dependence): %', pending;
    END IF;
END $$;

COMMIT;
