-- SAHOOL v9 — migrations/v9_rls_tenant_isolation.sql
-- إصلاح ثغرة عزل المستأجرين (IDOR عبر المستأجرين).
--
-- المشكلة: جداول أساسيّة لا RLS عليها، فمستأجر A يقرأ بيانات B بتخمين
-- المعرّفات. والمنصّة الآن تضبط app.current_tenant عبر tenant_connection()
-- في كلّ طلب — فهذه السياسات تُفعّل العزل فعليّاً.
--
-- مبدأ: tenant_id = current_setting('app.current_tenant'). NULL tenant
-- (بيانات قديمة بلا مستأجر) يُسمح بها فقط في التطوير عبر السماح بـNULL.
-- FORCE يضمن أنّ حتّى مالك الجدول يخضع للسياسة (دفاع قويّ).

-- دالّة مساعدة موحّدة (idempotent)
CREATE OR REPLACE FUNCTION _sahool_apply_tenant_rls(p_table TEXT)
RETURNS VOID AS $$
BEGIN
    -- فعّل RLS + FORCE
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', p_table);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', p_table);
    -- سياسة العزل (تُسقط القديمة أوّلاً للـidempotency)
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', p_table);
    EXECUTE format(
        'CREATE POLICY tenant_isolation ON %I USING ('
        '  tenant_id::TEXT = NULLIF(current_setting(''app.current_tenant'', true), '''')'
        ')', p_table
    );
END;
$$ LANGUAGE plpgsql;

-- طبّق على الجداول التي تحوي tenant_id (بحماية: فقط إن وُجد العمود والجدول)
DO $$
DECLARE
    t TEXT;
    tables TEXT[] := ARRAY[
        'fields',
        'field_lifecycle_transitions',
        'field_tasks',
        'agent_queries',
        'market_sales_listings',
        'soil_readings',
        'imagery_automation_fields'
    ];
    -- جداول لها سياسات في v10/v11/v12 لكن بلا FORCE → المالك (sahool_user)
    -- يتجاوز RLS! نضيف FORCE فقط (السياسة موجودة) لإغلاق هذا التجاوز.
    force_only TEXT[] := ARRAY[
        'commands',
        'field_lifecycle',
        'events',
        'trueup_calibrations',
        'sharing_keys',
        'onboarding_responses'
    ];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        -- الجدول موجود؟
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = t AND table_schema = 'public') THEN
            -- فيه عمود tenant_id؟
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = t AND column_name = 'tenant_id') THEN
                PERFORM _sahool_apply_tenant_rls(t);
                RAISE NOTICE 'RLS مُفعّل على %', t;
            ELSE
                RAISE NOTICE 'تخطّي % — لا عمود tenant_id (يحتاج إضافته أوّلاً)', t;
            END IF;
        ELSE
            RAISE NOTICE 'تخطّي % — الجدول غير موجود', t;
        END IF;
    END LOOP;

    -- إضافة FORCE فقط للجداول التي لها سياسات بالفعل (v10/v11/v12)
    -- بلا FORCE، مالك الجدول (sahool_user) يتجاوز RLS تماماً.
    FOREACH t IN ARRAY force_only LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = t AND table_schema = 'public') THEN
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
            RAISE NOTICE 'FORCE RLS على % (إغلاق تجاوز المالك)', t;
        END IF;
    END LOOP;
END $$;

-- ── P2-4: فهارس tenant_id لأداء RLS (الجداول الناقصة) ──────────
-- RLS يُرشّح كلّ استعلام بـtenant_id؛ بلا فهرس يتدهور الأداء مع النمو.
DO $$
DECLARE
    t TEXT;
    tables TEXT[] := ARRAY['fields','field_lifecycle','market_sales_listings','sharing_keys',
        'onboarding_responses'];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name=t AND column_name='tenant_id') THEN
            EXECUTE format(
                'CREATE INDEX IF NOT EXISTS idx_%s_tenant ON %I (tenant_id)', t, t);
            RAISE NOTICE 'فهرس tenant_id على %', t;
        END IF;
    END LOOP;
END $$;
