-- SAHOOL v70 — migrations/v70_rls_with_check_propagate.sql
-- عزل كتابة المستأجرين (WITH CHECK) — دفاع عمق على RLS (مراجعة أمنيّة).
--
-- الفجوة (مراجعة أمنيّة 🟠): سياسة tenant_isolation (v9) كانت USING-only — تعزل
-- القراءة فشل-مغلق، لكنّها لا تمنع الكتابة عبر المستأجرين: INSERT بـtenant_id لمستأجِر
-- آخر يمرّ، وكذا نقل صفّ بـUPDATE. الحماية كانت تتّكل كليّاً على كود التطبيق.
--
-- الإصلاح: v9 صار يعرّف السياسة بـWITH CHECK (عزل الكتابة). هذا الملفّ يَنشُر التغيير
-- على القواعد القائمة: يُعيد تطبيق الدالّة المساعدة _sahool_apply_tenant_rls (المُحدَّثة)
-- على **كلّ** جدول يحمل سياسة tenant_isolation — فيرتقي إلى WITH CHECK. (حلقة v56
-- تقتصر على الجداول بلا سياسة، فلا تلمس القائمة؛ لذا نحتاج هذا الـreapply الصريح.)
--
-- WITH CHECK محافظ: تحت سياق مستأجِر (app.current_tenant مضبوط) لا تُكتَب إلّا صفوف
-- tenant_id المطابق؛ بلا سياق (هجرات/مهامّ نظام) تُسمح الكتابة كما كانت (لا كسر).
-- idempotent بالكامل (إعادة التطبيق تُسقط/تُنشئ السياسة بنفس التعريف). آمن كلّ إقلاع.
--
-- الترتيب: يجب أن يلي v9 (تعريف الدالّة) وv56/v57 (التطبيق الديناميكيّ) في MANIFEST.

DO $$
DECLARE
    r RECORD;
    n INT := 0;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = '_sahool_apply_tenant_rls') THEN
        RAISE EXCEPTION 'v70: الدالّة المساعدة _sahool_apply_tenant_rls غير موجودة — طبّق v9 أوّلاً (تحقّق من ترتيب MANIFEST)';
    END IF;
    -- كلّ جدول يحمل سياسة tenant_isolation (أنشأتها الدالّة المساعدة) ⇒ أعِد تطبيقها
    -- لترتقي إلى WITH CHECK. الجداول ذات السياسات المخصّصة (أسماء أخرى) لا تُمَسّ.
    FOR r IN
        SELECT DISTINCT tablename
        FROM pg_policies
        WHERE schemaname = 'public' AND policyname = 'tenant_isolation'
    LOOP
        PERFORM _sahool_apply_tenant_rls(r.tablename);
        n := n + 1;
    END LOOP;
    RAISE NOTICE 'v70: أُعيد تطبيق WITH CHECK على % جدولاً (عزل الكتابة)', n;
END $$;
