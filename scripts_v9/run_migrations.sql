-- ═══════════════════════════════════════════════════════════════════
-- SAHOOL v9 — تطبيق الترحيلات بالترتيب الصحيح + تحقّق
-- ═══════════════════════════════════════════════════════════════════
-- الاستخدام:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts_v9/run_migrations.sql
--
-- الترتيب حرج: init_v8 (postgis + soil_readings) أوّلاً، ثمّ foundation
-- (fields)، ثمّ بقيّة v9، ثمّ v10/v11/v12 (commands/events/...)، ثمّ v13
-- (geospatial)، وأخيراً v9_rls_tenant_isolation (يضيف FORCE فوق السياسات).
--
-- ملاحظة: \i نسبيّ لمجلّد التشغيل. شغّل من جذر المشروع.
-- ═══════════════════════════════════════════════════════════════════

\set ON_ERROR_STOP on
\timing on

\echo '═══ ١. الأساس: PostGIS + الجداول الأوّليّة (soil_readings) ═══'
\i migrations/init_v8.sql

\echo '═══ ٢. الأساس v9 (fields + بذور) ═══'
\i migrations/v9_foundation.sql

\echo '═══ ٣. جداول v9 الإضافيّة ═══'
\i migrations/v9_new_tables.sql
\i migrations/v9_auth_improvements.sql
\i migrations/v9_market.sql
\i migrations/v9_odoo_bridge.sql
\i migrations/v9_automation.sql
\i migrations/v9_automation_persistence.sql
\i migrations/v9_onboarding.sql
\i migrations/v9_edge_idempotency.sql
\i migrations/v9_edge_occurred_at.sql
\i migrations/v9_lifecycle_occurred_at.sql
\i migrations/v9_append_only_enforcement.sql

\echo '═══ ٤. command store + lifecycle + events + trueup/sharing ═══'
\i migrations/v10_command_store_lifecycle.sql
\i migrations/v11_events_bus.sql
\i migrations/v12_trueup_sharing.sql

\echo '═══ ٥. الطبقة الجغرافيّة (trigger المساحة) ═══'
\i migrations/v13_geospatial_core.sql

\echo '═══ ٦. عزل المستأجرين RLS (FORCE + fail-closed) — أخيراً ═══'
\i migrations/v9_rls_tenant_isolation.sql

-- ─── تحقّق ما بعد الترحيل ───────────────────────────────────────────
\echo ''
\echo '═══ تحقّق: حالة RLS على الجداول الحسّاسة ═══'
\echo '(المتوقّع: rowsecurity=t و forcerowsecurity=t للكلّ)'
SELECT
    relname                AS "الجدول",
    relrowsecurity         AS "RLS مُفعّل",
    relforcerowsecurity    AS "FORCE مُفعّل"
FROM pg_class
WHERE relname IN (
    'commands', 'events', 'field_lifecycle', 'fields',
    'field_tasks', 'agent_queries', 'market_sales_listings',
    'soil_readings', 'trueup_calibrations', 'sharing_keys'
)
AND relkind = 'r'
ORDER BY relname;

\echo ''
\echo '═══ تحقّق: السياسات تستخدم app.current_tenant (لا app.tenant_id) ═══'
SELECT
    tablename   AS "الجدول",
    policyname  AS "السياسة",
    CASE WHEN qual LIKE '%app.current_tenant%' THEN '✓ صحيح'
         WHEN qual LIKE '%app.tenant_id%'      THEN '✗ خطأ (متغيّر قديم)'
         ELSE '؟ راجع يدويّاً' END AS "المتغيّر"
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename;

\echo ''
\echo '✅ اكتملت الترحيلات. شغّل اختبار العزل: test_tenant_isolation.sql'
