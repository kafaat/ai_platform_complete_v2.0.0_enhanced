-- SAHOOL v57 — migrations/v57_rls_dynamic_indexes.sql
-- تغطية فهارس tenant_id ديناميكيّة لأداء RLS.
--
-- المشكلة: RLS يُرشّح كلّ استعلام بـ
--   tenant_id = current_setting('app.current_tenant').
-- بلا فهرس btree صدارته tenant_id، يتحوّل الترشيح إلى مسح تسلسليّ
-- (sequential scan) فيتدهور الأداء صامتاً مع نموّ البيانات.
--
-- v9_rls_tenant_isolation.sql ينشئ الفهارس عبر مصفوفة ثابتة من ٥ جداول فقط.
-- لكن بعد v56_rls_dynamic_all (تغطية RLS ديناميكيّة) صار كثير من الجداول
-- يفرض ترشيح tenant_id بلا فهرس داعم. هذا الملفّ هو التوأم الطبيعيّ لـv56:
-- يُكمّل المصفوفة الثابتة بتغطية تلقائيّة لكلّ جدول.
--
-- يُطبَّق أخيراً (آخر سطر في MANIFEST بعد v56) كي توجد كلّ الجداول/الأعمدة.
-- idempotent: CREATE INDEX IF NOT EXISTS + تخطّي الجداول التي لها أصلاً
-- فهرس صدارته tenant_id ⇒ آمن إعادة التطبيق كلّ إقلاع.

DO $$
DECLARE
    r RECORD;
    n INT := 0;
BEGIN
    FOR r IN
        SELECT t.tablename
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
            WHERE ns.nspname = 'public' AND ic.relname = t.tablename AND a.attname = 'tenant_id'
          )
        ORDER BY t.tablename
    LOOP
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_tenant ON %I (tenant_id)',
                       r.tablename, r.tablename);
        RAISE NOTICE 'v57_rls_dynamic_indexes: created tenant_id index on %', r.tablename;
        n := n + 1;
    END LOOP;
    RAISE NOTICE 'v57_rls_dynamic_indexes: indexes created = %', n;
END $$;
