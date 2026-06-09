-- SAHOOL v9 — migrations/v9_rls_force_all.sql
-- ─────────────────────────────────────────────────────────────────────────
-- FIX (أمان): توحيد فرض RLS. كان 7 جداول فقط من 26 تستخدم FORCE ROW LEVEL
-- SECURITY؛ الـ19 الباقية تُفعّل RLS في ترحيلاتها (ENABLE) لكن دون FORCE، فإن
-- اتّصل التطبيق بدور **مالك الجدول** تُتجاوَز سياسة العزل على تلك الجداول
-- (events, commands, field_boundaries, users, audit_log, field_lifecycle…)
-- ⇒ تسرّب بيانات عبر المستأجرين. هذا الترحيل يفرض RLS على كلّ جدول مُفعَّل.
--
-- يُطبَّق **أخيراً** في MANIFEST (بعد إنشاء كلّ الجداول وتفعيل RLS عليها).
-- ملاحظة تشغيليّة مكمّلة: يجب ألّا يكون دور تطبيق الإنتاج superuser ولا
-- BYPASSRLS، وإلّا يتجاوز RLS كليّاً بغضّ النظر عن FORCE.
-- ─────────────────────────────────────────────────────────────────────────

DO $$
DECLARE
    r RECORD;
    n INT := 0;
BEGIN
    FOR r IN
        SELECT relname
        FROM pg_class
        WHERE relkind = 'r'
          AND relnamespace = 'public'::regnamespace
          AND relrowsecurity            -- RLS مُفعَّل
          AND NOT relforcerowsecurity   -- لكن غير مفروض
        ORDER BY relname
    LOOP
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', r.relname);
        n := n + 1;
    END LOOP;
    RAISE NOTICE 'v9_rls_force_all: forced RLS on % previously-unforced table(s)', n;
END $$;
