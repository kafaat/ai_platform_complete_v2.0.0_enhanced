-- تراجع v237_tenant_isolation_hardening — يدويّ فقط (ليس في MANIFEST).
-- ⚠ التراجع يعيد فتح تسرّبات عزل المستأجرين المقيسة (T1/T2/T7/T8/T9) — لا تشغّله على إنتاج حيّ
--   إلّا لإبطال عطل وظيفيّ سبّبه v237، وبقرار مالك.
--
-- • السياسات: تُستعاد شروطها السابقة من COMMENT ON POLICY ('v237-prev:{json}') الذي كتبه v237 قبل
--   كلّ تعديل، ثمّ يُعاد تشغيل v206 (آخر مدخل دائماً) لأنّ v237 يسبقه فبعض اللقطات قبل v206.
-- • VIEWs: تُعاد إلى صلاحيّات المالك (RESET security_invoker) للخمسة التي عالجها v237 فقط.
-- • T9: تُسقَط قيود chk_<table>_tenant_nonempty.
-- • T3: لا يُعاد EXECUTE دوالّ DEFINER للإدخال إلى sahool_app — لم تمنحه هجرةٌ أصلاً (المنح الشامل
--   من سكربتَي bootstrap)، وإعادته تعيد تسرّب normalized_payload عبر المستأجرين.
--
-- الاستعمال (من مجلّد المستودع):  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/v237_tenant_isolation_hardening.down.sql

BEGIN;

DO $$
DECLARE
    pol record;
    prev jsonb;
BEGIN
    FOR pol IN
        SELECT p.tablename, p.policyname,
               obj_description(po.oid, 'pg_policy') AS note
        FROM pg_policies p
        JOIN pg_policy po ON po.polname = p.policyname
                         AND po.polrelid = format('public.%I', p.tablename)::regclass
        WHERE p.schemaname = 'public'
          AND obj_description(po.oid, 'pg_policy') LIKE 'v237-prev:%'
    LOOP
        prev := substr(pol.note, length('v237-prev:') + 1)::jsonb;
        IF prev ->> 'with_check' IS NULL THEN
            EXECUTE format('ALTER POLICY %I ON public.%I USING (%s)',
                           pol.policyname, pol.tablename, prev ->> 'qual');
        ELSE
            EXECUTE format('ALTER POLICY %I ON public.%I USING (%s) WITH CHECK (%s)',
                           pol.policyname, pol.tablename, prev ->> 'qual', prev ->> 'with_check');
        END IF;
        EXECUTE format('COMMENT ON POLICY %I ON public.%I IS NULL', pol.policyname, pol.tablename);
    END LOOP;
END $$;

DO $$
DECLARE v text;
BEGIN
    FOREACH v IN ARRAY ARRAY['v_event_dead_letter', 'v_entity_latest_event', 'v_latest_ndvi',
                             'v_field_summary', 'v_farm_stats'] LOOP
        IF to_regclass(format('public.%I', v)) IS NOT NULL THEN
            EXECUTE format('ALTER VIEW public.%I RESET (security_invoker)', v);
        END IF;
    END LOOP;
END $$;

DO $$
DECLARE k record;
BEGIN
    FOR k IN
        SELECT c.conrelid::regclass AS rel, c.conname
        FROM pg_constraint c
        WHERE c.connamespace = 'public'::regnamespace AND c.contype = 'c'
          AND c.conname LIKE 'chk\_%\_tenant\_nonempty'
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', k.rel, k.conname);
    END LOOP;
END $$;

COMMIT;

-- v206 يرى الحالة النهائيّة دائماً: يُعاد تشغيله كي لا يبقى ما قبل v206 من اللقطات.
\ir v206_rls_final_hardening.sql
