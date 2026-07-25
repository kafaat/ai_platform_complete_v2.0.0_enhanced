-- v206_rls_final_hardening.sql — تصليب RLS النهائيّ (حزمة 72 ساعة، DB-P0-06/DB-P0-07).
--
-- (1) كتابة fail-closed: سياسة tenant_isolation العامّة (v9/v56) كانت تسمح
--     INSERT/UPDATE بلا app.current_tenant (هروب IS NULL لصالح الهجرات/المهامّ).
--     لكنّ الهجرات تعمل بدور المالك superuser (يتجاوز RLS كلّيًّا) ومهامّ النظام
--     تعمل بدور BYPASSRLS — فالهروب غير لازم، وبقاؤه يسمح لدور runtime
--     (sahool_app NOBYPASSRLS) نسيَ set_config بكتابة صفّ لمستأجرٍ آخر.
--     هذا الملفّ يشدّد WITH CHECK: بلا سياق مستأجر ⇒ الكتابة تفشل دائمًا.
--     الجداول ذات tenant_id القابل للنُّل تحتفظ بسلوك الصفوف النظاميّة
--     (tenant_id IS NULL) كما في v122.
-- (2) تأكيد catalog دائم: أيّ جدول عامّ فيه عمود tenant_id يجب أن يكون
--     RLS ENABLED + FORCED + سياسة كتابة واحدة على الأقلّ بـWITH CHECK —
--     وإلّا EXCEPTION يمنع تسرب جدول مستقبليّ منسيّ. (فحص الفهرس المقترح
--     WARNING فقط — مرشّحون يحتاجون تحقّق catalog حيًّا، لا إثبات قاطع.)
--
-- يجب أن يبقى آخر مدخل في MANIFEST.txt دائمًا (يرى الحالة النهائيّة للسياسات).
-- idempotent وآمن على إعادة التشغيل.

-- (0) حارس ترتيب: v122 يجب أن يسبق (sahool_effective_tenant_id).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = 'sahool_effective_tenant_id'
    ) THEN
        RAISE EXCEPTION 'v206: public.sahool_effective_tenant_id غير موجودة — طبّق v122 قبل هذا الملفّ (تحقّق من ترتيب MANIFEST.txt)';
    END IF;
END $$;

-- (1) تشديد WITH CHECK لكلّ سياسة tenant_isolation عامّة (USING يبقى كما هو).
DO $$
DECLARE
    pol record;
    tenant_nullable boolean;
    predicate text;
    n int := 0;
BEGIN
    FOR pol IN
        SELECT p.schemaname, p.tablename, p.policyname, p.with_check
        FROM pg_policies p
        WHERE p.schemaname = 'public'
          AND p.policyname = 'tenant_isolation'
          AND p.cmd IN ('ALL', 'INSERT', 'UPDATE')
          AND p.with_check IS NOT NULL
          -- الهروب القديم: يسمح بالكتابة بلا سياق مستأجر.
          AND p.with_check ILIKE '%current_setting%IS NULL%'
    LOOP
        SELECT (c.is_nullable = 'YES') INTO tenant_nullable
        FROM information_schema.columns c
        WHERE c.table_schema = pol.schemaname
          AND c.table_name = pol.tablename
          AND c.column_name = 'tenant_id';

        -- تخطَّ الجداول بلا عمود tenant_id: عزلها المستأجريّ يمرّ عبر جدول أب
        -- (مثال: field_lifecycle_transitions ← field_lifecycle.tenant_id عبر lifecycle_id)،
        -- فإعادة كتابة WITH CHECK إلى (tenant_id = …) تفشل («column tenant_id does not exist»)
        -- وتهدم العزل الأبويّ الصحيح. تأكيد catalog (2) يقتصر أصلاً على جداول tenant_id.
        IF NOT FOUND THEN
            CONTINUE;
        END IF;

        IF tenant_nullable THEN
            -- صفوف نظاميّة بلا مستأجر تبقى ممكنة؛ صفّ بمستأجر يتطلّب السياق المطابق.
            predicate := '(tenant_id IS NULL OR tenant_id::text = public.sahool_effective_tenant_id())';
        ELSE
            predicate := '(tenant_id::text = public.sahool_effective_tenant_id())';
        END IF;

        EXECUTE format(
            'ALTER POLICY %I ON %I.%I WITH CHECK (%s)',
            pol.policyname, pol.schemaname, pol.tablename, predicate
        );
        n := n + 1;
        RAISE NOTICE 'v206: tenant_isolation fail-closed writes على %', pol.tablename;
    END LOOP;
    RAISE NOTICE 'v206: سياسات شُدّدت = %', n;
END $$;

-- (2) تأكيد catalog النهائيّ الدائم: لا جدول tenant بلا RLS تامّ.
DO $$
DECLARE
    offenders text;
BEGIN
    SELECT string_agg(t.tablename, ', ' ORDER BY t.tablename) INTO offenders
    FROM pg_tables t
    WHERE t.schemaname = 'public'
      AND EXISTS (SELECT 1 FROM information_schema.columns c
                  WHERE c.table_schema = 'public' AND c.table_name = t.tablename
                    AND c.column_name = 'tenant_id')
      AND (
          NOT t.rowsecurity
          OR NOT EXISTS (SELECT 1 FROM pg_class c
                         WHERE c.relname = t.tablename
                           AND c.relnamespace = 'public'::regnamespace
                           AND c.relforcerowsecurity)
          OR NOT EXISTS (SELECT 1 FROM pg_policies p
                         WHERE p.schemaname = 'public' AND p.tablename = t.tablename
                           AND p.cmd IN ('ALL', 'INSERT', 'UPDATE')
                           AND p.with_check IS NOT NULL)
      );
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION 'v206 catalog assertion: جداول tenant بلا RLS كامل (ENABLE+FORCE+WITH CHECK): %', offenders;
    END IF;
END $$;

-- (2ب) فهرس tenant-leading مقترح — تحذير فقط (مرشّحون، لا إثبات قاطع).
DO $$
DECLARE
    missing text;
BEGIN
    SELECT string_agg(t.tablename, ', ' ORDER BY t.tablename) INTO missing
    FROM pg_tables t
    WHERE t.schemaname = 'public'
      AND EXISTS (SELECT 1 FROM information_schema.columns c
                  WHERE c.table_schema = 'public' AND c.table_name = t.tablename
                    AND c.column_name = 'tenant_id')
      AND NOT EXISTS (
          SELECT 1 FROM pg_indexes i
          WHERE i.schemaname = 'public' AND i.tablename = t.tablename
            AND i.indexdef ~* '\((tenant_id|"?tenant_id"?)\s*[,)]'
      );
    IF missing IS NOT NULL THEN
        RAISE WARNING 'v206: جداول tenant بلا فهرس يبدأ بـtenant_id (مرشّحون لتحقّق catalog حيّ): %', missing;
    END IF;
END $$;
