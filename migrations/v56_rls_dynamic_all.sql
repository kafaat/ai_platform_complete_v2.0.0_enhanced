-- SAHOOL v56 — migrations/v56_rls_dynamic_all.sql
-- تغطية RLS ديناميكيّة شاملة (catch-all) — اكتشاف تلقائيّ للجداول.
--
-- المشكلة: في v9_rls_tenant_isolation.sql يُطبَّق عزل المستأجرين عبر مصفوفات
-- جداول مكتوبة يدويّاً (tables TEXT[] := ARRAY['fields','field_tasks',...]).
-- أيّ جدول جديد يحوي tenant_id ينساه أحدهم من تلك المصفوفات يبقى بلا عزل
-- صامتاً ⇒ تسرّب بين المستأجرين. هذا الملفّ يجعل التغطية تلقائيّة للأبد.
--
-- ماذا يفعل: يمسح كلّ جدول أساسيّ (BASE TABLE) في schema=public يحوي عمود
-- tenant_id لكنّه بلا أيّ سياسة RLS قائمة، ويطبّق عليه سياسة العزل الموحّدة
-- عبر الدالّة المساعدة _sahool_apply_tenant_rls (المعرّفة في
-- v9_rls_tenant_isolation.sql). فيُغطّي الجداول المنسيّة والمستقبليّة دون تعديل.
--
-- يُكمّل ولا يستبدل: المصفوفات الصريحة في v9_rls_tenant_isolation.sql تبقى
-- مرجع التوثيق الواضح؛ هذا الملفّ سادّ ثغرات (gap-closer) فقط.
--
-- سلامة حرجة — لماذا «بلا سياسة قائمة» شرطٌ إلزاميّ:
-- PostgreSQL يدمج السياسات الـPERMISSIVE المتعدّدة بـOR. فإضافة
-- tenant_isolation إلى جدول له سياسته الخاصّة (sharing_keys_owner,
-- user_self, user_own_prefs, audit_log_policy, commands_tenant_isolation,
-- events_tenant_isolation, ...) ستوسّع الوصول بـOR وتُضعِف تلك النماذج
-- المقصودة. لذلك تقتصر الحلقة على الجداول التي لها tenant_id وصفر سياسات —
-- فتصبح سادّ ثغرات نقيّاً لا يلمس الجداول المحميّة سلفاً أبداً.
--
-- الترتيب: يُطبَّق أخيراً في MANIFEST كي تكون كلّ الجداول والأعمدة موجودة.
--
-- متطلّب تشغيليّ (يُعاد التأكيد): يجب أن يكون دور التطبيق (sahool_app)
-- غيرَ superuser وذا NOBYPASSRLS (راجع PR الخاصّ بـsahool_app)، وإلّا
-- يُتجاوَز RLS بالكامل مهما طُبّقت السياسات.

DO $$
DECLARE
    r RECORD;
    n INT := 0;
BEGIN
    -- حارس: تأكّد من وجود الدالّة المساعدة (يلتقط أيّ خطأ في ترتيب MANIFEST بصوتٍ عالٍ)
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = '_sahool_apply_tenant_rls') THEN
        RAISE EXCEPTION 'v56_rls_dynamic_all: الدالّة المساعدة _sahool_apply_tenant_rls غير موجودة — يجب تطبيق v9_rls_tenant_isolation.sql قبل هذا الملفّ (تحقّق من ترتيب MANIFEST.txt)';
    END IF;

    FOR r IN
        SELECT t.tablename
        FROM pg_tables t
        WHERE t.schemaname = 'public'
          AND EXISTS (SELECT 1 FROM information_schema.columns c
                      WHERE c.table_schema='public' AND c.table_name=t.tablename
                        AND c.column_name='tenant_id')
          AND NOT EXISTS (SELECT 1 FROM pg_policies p
                          WHERE p.schemaname='public' AND p.tablename=t.tablename)
        ORDER BY t.tablename
    LOOP
        PERFORM _sahool_apply_tenant_rls(r.tablename);
        RAISE NOTICE 'v56_rls_dynamic_all: applied tenant RLS to %', r.tablename;
        n := n + 1;
    END LOOP;

    RAISE NOTICE 'v56_rls_dynamic_all: إجماليّ الجداول المُغطّاة ديناميكيّاً = %', n;
END $$;
