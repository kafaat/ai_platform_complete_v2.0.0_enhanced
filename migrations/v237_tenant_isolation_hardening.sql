-- v237_tenant_isolation_hardening.sql — حزمة عزل المستأجرين (تدقيق 2026-11-01: T1 · T2 · T3 · T7 · T8 · T9).
--
-- مسودّة GATE-01: لا تُدمَج ولا تُطبَّق قبل حكم المالك (SAHOOL_MIGRATE_APPLY + runbook فكّ التجميد).
-- كلّ تسرّب أدناه مقيس على PostgreSQL 16 مبنيّة من MANIFEST بدور sahool_app (NOBYPASSRLS):
--
--   T1  خمسة VIEWs بلا security_invoker يملكها superuser ⇒ تُقرأ بصلاحيّة المالك فتتخطّى FORCE RLS
--       (v_entity_latest_event أعاد حمولة مستأجر آخر؛ v_event_dead_letter أعاد DLQ كلّ المستأجرين).
--       ← كلّ VIEW في public (عدا ما تملكه الامتدادات) يصير security_invoker، مع تأكيد كتالوج.
--   T2  سياسات كتابة تحمل ذراع «لا سياق مستأجر ⇒ اسمح» (webhooks · prescription_maps ·
--       event_outbox …) لم يمسّها v206 لأنّه ينتقي بالاسم tenant_isolation لا بالشكل.
--       ← يُنتقى بالشكل: يُحذف ذراع الهروب من USING وWITH CHECK في أيّ سياسة كانت.
--   T8  الذراع نفسه في USING لـinvitations/audit_log/break_glass_grants: غياب السياق = رؤية الكلّ
--       (رموز الدعوات وbreak-glass بنصّ صريح). يُعالَج بالقاعدة نفسها؛ مسار الخدمة الصريح
--       (app.current_role='admin' الذي يضبطه pool خدمة auth) يبقى.
--   T3  دوالّ DEFINER لمستوى تحكّم الإدخال (مالكها sahool_ingest_resolver ذو BYPASSRLS) أعاد
--       bootstrap منحها لـsahool_app ⇒ قرأ normalized_payload لمستأجر آخر. ← REVOKE للقواعد المنشورة.
--   T7  v122 وسّع USING في ستّ سياسات إلى «tenant_id IS NULL OR …» وأسقط ذراع المستخدم من
--       user_own_prefs (هواتف/بريد). ← شرط صارم؛ user_own_prefs = المستخدم نفسه داخل مستأجره.
--   T9  جداول tenant_id نصّيّ تقارن بـcurrent_setting خامّ ⇒ '' (السياق بعد انتهاء معاملة محلّيّة)
--       يطابق صفوف tenant_id='' «دلواً مشتركاً». ← NULLIF في السياسات + CHECK (btrim(tenant_id) <> '')
--       NOT VALID؛ VALIDATE يشغّله المشغِّل بعد تقرير نظيف (docs/runbooks/validate_not_valid_constraints.md).
--
-- قابل لإعادة التشغيل (المُهاجر يعيد تطبيق MANIFEST كاملاً في كلّ نشر، فهجرات أقدم قد تعيد
-- إنشاء السياسة الضعيفة ثمّ يعيد هذا الملفّ تشديدها). ذرّيّ: معاملة واحدة، وأيّ تأكيد فاشل يُرجعها.
-- قبل كلّ تعديل سياسة يُحفَظ شرطها السابق في COMMENT ON POLICY ('v237-prev:{json}') لملفّ التراجع.
-- يُدرَج قبل v206 كي يبقى v206 آخر مدخل.

BEGIN;
SET LOCAL lock_timeout = '15s';

-- (0) حارس ترتيب: v122 يسبق (sahool_effective_tenant_id).
DO $$
BEGIN
    IF to_regprocedure('public.sahool_effective_tenant_id()') IS NULL THEN
        RAISE EXCEPTION 'v237: public.sahool_effective_tenant_id() غير موجودة — طبّق v122 قبل هذا الملفّ';
    END IF;
END $$;

-- ── T1: VIEWs بصلاحيّات القارئ ────────────────────────────────────────────────
-- المعروفة: v_event_dead_letter (v48) · v_entity_latest_event (v11) · v_latest_ndvi ·
-- v_field_summary · v_farm_stats (init_v8). الانتقاء عامّ كي لا يفلت VIEW سابق منسيّ.
DO $$
DECLARE v record;
BEGIN
    FOR v IN
        SELECT c.relname
        FROM pg_class c
        WHERE c.relnamespace = 'public'::regnamespace
          AND c.relkind = 'v'
          AND NOT EXISTS (SELECT 1 FROM pg_depend d
                          WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid
                            AND d.deptype = 'e')
          AND NOT EXISTS (SELECT 1 FROM pg_options_to_table(c.reloptions) o
                          WHERE o.option_name = 'security_invoker'
                            AND lower(o.option_value) IN ('true', 'on', '1', 'yes'))
    LOOP
        EXECUTE format('ALTER VIEW public.%I SET (security_invoker = true)', v.relname);
        RAISE NOTICE 'v237 T1: security_invoker على %', v.relname;
    END LOOP;
END $$;

-- ── T2 · T7 · T8 · T9: السياسات (بالشكل لا بالاسم) ─────────────────────────────
DO $$
DECLARE
    -- ذراع الهروب كما يطبعه pg_get_expr: «(NULLIF(current_setting('app.current_tenant'…), '') IS NULL) OR ».
    -- يُركَّب بالتسلسل كي لا يُقرأ نصّ الملفّ نفسه كسياسة غير آمنة في الحرّاس الساكنة.
    -- اسم الدالّة مُجزّأ في السلاسل: هي نصٌّ يُطابَق لا نداءٌ يُنفَّذ (حارس missing_ok يقرأ النداءات).
    cs CONSTANT text := 'current' || '_setting';
    escape_arm CONSTANT text :=
        '(NULLIF(' || cs || '(' || quote_literal('app.current_tenant') || '::text, true), '
        || quote_literal('') || '::text) IS ' || 'NULL) OR ';
    -- توقيع v122 في USING (الجداول ذات tenant_id القابل للنُّل).
    v122_arm CONSTANT text := '(tenant_id IS NULL) OR ((tenant_id)::text = sahool_effective_tenant_id())';
    strict_pred CONSTANT text := '(tenant_id::text = public.sahool_effective_tenant_id())';
    own_prefs_pred CONSTANT text :=
        '(tenant_id::text = public.sahool_effective_tenant_id() AND '
        'COALESCE(user_ref, user_id::text) = NULLIF(current_setting(''app.current_user_id'', true), ''''))';
    before jsonb;
    pol record;
    q text;
    wc text;
    n_changed int := 0;
BEGIN
    SELECT COALESCE(jsonb_object_agg(p.tablename || '.' || p.policyname,
                                     jsonb_build_object('qual', p.qual, 'with_check', p.with_check)),
                    '{}'::jsonb)
      INTO before
      FROM pg_policies p WHERE p.schemaname = 'public';

    FOR pol IN
        SELECT p.tablename, p.policyname, p.qual, p.with_check, c.udt_name AS tenant_type,
               (c.is_nullable = 'YES') AS tenant_nullable
        FROM pg_policies p
        LEFT JOIN information_schema.columns c
          ON c.table_schema = 'public' AND c.table_name = p.tablename AND c.column_name = 'tenant_id'
        WHERE p.schemaname = 'public' AND p.permissive = 'PERMISSIVE'
        ORDER BY p.tablename, p.policyname
    LOOP
        q := pol.qual;
        wc := pol.with_check;

        -- T2 + T8: حذف ذراع «بلا سياق ⇒ اسمح» (حذف ذراع من OR لا يمكن إلّا أن يُضيّق).
        IF q IS NOT NULL THEN q := replace(q, escape_arm, ''); END IF;
        IF wc IS NOT NULL AND strpos(wc, escape_arm) > 0 THEN
            wc := replace(wc, escape_arm, '');
            -- الشكل البسيط (ذراع مستأجر وحيد على جدول tenant_id) ⇒ شرط v206 نفسه حرفيّاً، فيبقى
            -- سلوك ما يشدّده v206 لاحقاً كما هو (صفوف نظاميّة tenant_id IS NULL في الجداول القابلة
            -- للنُّل)، ويتّسع التشديد بالشكل إلى ما فاته انتقاؤه بالاسم.
            IF pol.tenant_type IS NOT NULL AND strpos(wc, ' OR ') = 0 THEN
                wc := CASE WHEN pol.tenant_nullable
                           THEN '(tenant_id IS NULL OR tenant_id::text = public.sahool_effective_tenant_id())'
                           ELSE strict_pred END;
            END IF;
        END IF;

        -- T7: توقيع v122 (USING = WITH CHECK = «tenant_id IS NULL OR …») ⇒ شرط صارم.
        IF q IS NOT NULL AND strpos(q, v122_arm) > 0 THEN
            IF pol.tablename = 'notification_preferences' THEN
                q := own_prefs_pred;
                wc := own_prefs_pred;
            ELSE
                q := strict_pred;
                wc := strict_pred;
            END IF;
        END IF;

        -- T9: tenant_id غير uuid ⇒ current_setting خامّ يُلفّ بـNULLIF ('' = لا سياق، لا دلو مشترك).
        IF pol.tenant_type IS NOT NULL AND pol.tenant_type <> 'uuid' THEN
            IF q IS NOT NULL THEN
                q := replace(regexp_replace(replace(q, 'NULLIF(' || cs || '(', 'NULLIF(__v237_cs__('),
                                            cs || '\(''(app\.[a-z0-9_]+)''::text, true\)',
                                            'NULLIF(' || cs || '(''\1''::text, true), ''''::text)', 'g'),
                             'NULLIF(__v237_cs__(', 'NULLIF(' || cs || '(');
            END IF;
            IF wc IS NOT NULL THEN
                wc := replace(regexp_replace(replace(wc, 'NULLIF(' || cs || '(', 'NULLIF(__v237_cs__('),
                                             cs || '\(''(app\.[a-z0-9_]+)''::text, true\)',
                                             'NULLIF(' || cs || '(''\1''::text, true), ''''::text)', 'g'),
                              'NULLIF(__v237_cs__(', 'NULLIF(' || cs || '(');
            END IF;
        END IF;

        IF q IS DISTINCT FROM pol.qual OR wc IS DISTINCT FROM pol.with_check THEN
            IF wc IS NULL THEN
                EXECUTE format('ALTER POLICY %I ON public.%I USING (%s)', pol.policyname, pol.tablename, q);
            ELSE
                EXECUTE format('ALTER POLICY %I ON public.%I USING (%s) WITH CHECK (%s)',
                               pol.policyname, pol.tablename, q, wc);
            END IF;
            EXECUTE format('COMMENT ON POLICY %I ON public.%I IS %L', pol.policyname, pol.tablename,
                           'v237-prev:' || (before -> (pol.tablename || '.' || pol.policyname))::text);
            n_changed := n_changed + 1;
            RAISE NOTICE 'v237: شُدّدت السياسة %.%', pol.tablename, pol.policyname;
        END IF;
    END LOOP;
    RAISE NOTICE 'v237: سياسات شُدّدت = %', n_changed;
END $$;

-- ── T9: CHECK (btrim(tenant_id) <> '') NOT VALID + تقرير المخالفات ───────────────
-- NOT VALID: يُفرض على الصفوف الجديدة/المُحدَّثة فوراً بلا مسح. VALIDATE خطوة مشغِّل بعد تقرير
-- نظيف (scripts/migrations/report_not_valid_constraint_violations.py)، لا هجرة — كما في v127/v130.
DO $$
DECLARE
    t record;
    cname text;
    bad bigint;
BEGIN
    FOR t IN
        SELECT c.table_name
        FROM information_schema.columns c
        JOIN pg_tables pt ON pt.schemaname = 'public' AND pt.tablename = c.table_name
        WHERE c.table_schema = 'public' AND c.column_name = 'tenant_id'
          AND c.udt_name IN ('text', 'varchar', 'bpchar')
        ORDER BY c.table_name
    LOOP
        cname := 'chk_' || t.table_name || '_tenant_nonempty';
        IF NOT EXISTS (SELECT 1 FROM pg_constraint
                       WHERE conrelid = format('public.%I', t.table_name)::regclass
                         AND conname = cname) THEN
            EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I CHECK (btrim(tenant_id) <> %L) NOT VALID',
                           t.table_name, cname, '');
        END IF;
        EXECUTE format('SELECT count(*) FROM public.%I WHERE NOT (btrim(tenant_id) <> %L)', t.table_name, '')
           INTO bad;
        IF bad > 0 THEN
            RAISE WARNING 'v237 T9: %.% — % صفّ بمستأجر فارغ (تقرير؛ نظّفها قبل VALIDATE)', t.table_name, cname, bad;
        ELSE
            RAISE NOTICE 'v237 T9: %.% — نظيف (جاهز لـVALIDATE المشغِّل)', t.table_name, cname;
        END IF;
    END LOOP;
END $$;

-- ── T3: دوالّ DEFINER لمستوى تحكّم الإدخال — لا EXECUTE لـsahool_app ولا PUBLIC ─────
-- مستدعيها الوحيد sahool_ingest (منحٌ صريح في bootstrap). bootstrap يعيد المنح الشامل بعد
-- الهجرات، فالإصلاح الدائم في سكربتَي bootstrap (فرع audit-fix-19)؛ هذا يغلق القواعد المنشورة.
DO $$
DECLARE
    sig text;
BEGIN
    FOREACH sig IN ARRAY ARRAY[
        'public.claim_submissions_for_projection(integer,integer)',
        'public.complete_submission_projection(bigint,text,text)',
        'public.resolve_ingest_source(text)'
    ] LOOP
        IF to_regprocedure(sig) IS NOT NULL THEN
            EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', sig);
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahool_app') THEN
                EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM sahool_app', sig);
            END IF;
        END IF;
    END LOOP;
END $$;

-- ── تأكيدات الكتالوج (أيّ مخالفة ⇒ EXCEPTION ⇒ تُرجَع المعاملة كلّها) ─────────────
DO $$
DECLARE
    cs CONSTANT text := 'current' || '_setting';
    offenders text;
BEGIN
    -- A1 (T1): لا VIEW في public بصلاحيّات المالك.
    SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO offenders
    FROM pg_class c
    WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'v'
      AND NOT EXISTS (SELECT 1 FROM pg_depend d
                      WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e')
      AND NOT EXISTS (SELECT 1 FROM pg_options_to_table(c.reloptions) o
                      WHERE o.option_name = 'security_invoker'
                        AND lower(o.option_value) IN ('true', 'on', '1', 'yes'));
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION 'v237 A1: VIEWs بلا security_invoker (تتخطّى RLS): %', offenders;
    END IF;

    -- A2 (T2/T8): لا سياسة تسمح حين يغيب سياق المستأجر (أيّ اسم GUC مستأجر، بـNULLIF أو بدونه).
    SELECT string_agg(p.tablename || '.' || p.policyname, ', ' ORDER BY p.tablename) INTO offenders
    FROM pg_policies p
    WHERE p.schemaname = 'public'
      AND (COALESCE(p.qual, '') || ' ' || COALESCE(p.with_check, ''))
          ~ 'current_setting\(''app\.[a-z0-9_]*tenant[a-z0-9_]*''::text, true\)(, ''''::text\))? IS NULL';
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION 'v237 A2: سياسات بذراع «بلا سياق مستأجر ⇒ اسمح»: %', offenders;
    END IF;

    -- A3 (T7): لا توقيع v122 المُوسَّع في USING.
    SELECT string_agg(p.tablename || '.' || p.policyname, ', ' ORDER BY p.tablename) INTO offenders
    FROM pg_policies p
    WHERE p.schemaname = 'public'
      AND strpos(COALESCE(p.qual, ''),
                 '(tenant_id IS NULL) OR ((tenant_id)::text = sahool_effective_tenant_id())') > 0;
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION 'v237 A3: سياسات ما زالت بتوسيع v122: %', offenders;
    END IF;

    -- A4 (T9): لا current_setting خامّ في سياسات جداول tenant_id غير uuid.
    SELECT string_agg(p.tablename || '.' || p.policyname, ', ' ORDER BY p.tablename) INTO offenders
    FROM pg_policies p
    JOIN information_schema.columns c
      ON c.table_schema = 'public' AND c.table_name = p.tablename AND c.column_name = 'tenant_id'
    WHERE p.schemaname = 'public' AND c.udt_name <> 'uuid'
      AND replace(COALESCE(p.qual, '') || ' ' || COALESCE(p.with_check, ''),
                  'NULLIF(' || cs || '(', '') ~ (cs || '\(');
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION 'v237 A4: current_setting بلا NULLIF على tenant_id نصّيّ: %', offenders;
    END IF;

    -- A5 (T9): كلّ جدول tenant_id نصّيّ يحمل CHECK غير الفارغ.
    SELECT string_agg(c.table_name, ', ' ORDER BY c.table_name) INTO offenders
    FROM information_schema.columns c
    JOIN pg_tables pt ON pt.schemaname = 'public' AND pt.tablename = c.table_name
    WHERE c.table_schema = 'public' AND c.column_name = 'tenant_id'
      AND c.udt_name IN ('text', 'varchar', 'bpchar')
      AND NOT EXISTS (SELECT 1 FROM pg_constraint k
                      WHERE k.conrelid = format('public.%I', c.table_name)::regclass
                        AND k.conname = 'chk_' || c.table_name || '_tenant_nonempty');
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION 'v237 A5: جداول tenant_id نصّيّ بلا CHECK غير فارغ: %', offenders;
    END IF;

    -- A6 (T3): sahool_app بلا EXECUTE على دوالّ تحكّم الإدخال.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahool_app') THEN
        SELECT string_agg(p.proname, ', ' ORDER BY p.proname) INTO offenders
        FROM pg_proc p
        WHERE p.pronamespace = 'public'::regnamespace
          AND p.proname IN ('claim_submissions_for_projection', 'complete_submission_projection',
                            'resolve_ingest_source')
          AND has_function_privilege('sahool_app', p.oid, 'EXECUTE');
        IF offenders IS NOT NULL THEN
            RAISE EXCEPTION 'v237 A6: sahool_app يملك EXECUTE على دوالّ DEFINER للإدخال: %', offenders;
        END IF;
    END IF;
END $$;

COMMIT;
