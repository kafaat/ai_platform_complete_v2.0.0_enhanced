-- migrations/v71_rls_missing_tables.sql
--
-- MEDIUM-009 (تدقيق خارجيّ): جداول تحمل بيانات لكلّ مستأجِر لكنّها بلا سياسة RLS
-- مباشرة لأنّها لا تملك عمود tenant_id بنفسها (تُعزَل عبر مفتاح أجنبيّ). حارس
-- test_rls_tenant_coverage يفحص الجداول ذات عمود tenant_id فقط، ففاتته هذه — لكنّ
-- استعلاماً مباشراً عليها (بلا JOIN للأب) يُسرِّب صفوف مستأجِرين آخرين.
--
-- ١) field_lifecycle_transitions: يُعزَل عبر lifecycle_id → field_lifecycle (الذي
--    يحمل tenant_id وله RLS). كلّ مساراته تقرأ تحت سياق المستأجِر (tenant_connection)
--    ⇒ سياسة fail-closed مبنيّة على الأب آمنة (تطابق نمط _sahool_apply_tenant_rls).
--
-- ملاحظة على weather_automation_locations (طُرِح في نفس النتيجة): **لا** يُطبَّق عليه
-- RLS هنا قصداً. الكود (weather_automation.py) يوثّق أنّه **عابر للمستأجرين بالتصميم**:
-- مجدوِل خلفيّ يقرأ كلّ الإحداثيّات المسجّلة عبر المستأجرين بلا ضبط app.current_tenant،
-- فسياسة fail-closed تُعيد صفر صفوف فتكسر المجدوِل. الإصلاح الصحيح هناك دورٌ خدميّ
-- مخصّص (BYPASSRLS) لمسار المجدوِل — متابعة نشر، لا RLS على الجدول. (البيانات: إحداثيّات
-- مقرّبة + field_id، حسّاسيّة منخفضة.) يبقى موثّقاً في الحارس كـ«عالميّ عمداً».

BEGIN;

ALTER TABLE field_lifecycle_transitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_lifecycle_transitions FORCE ROW LEVEL SECURITY;

-- idempotent
DROP POLICY IF EXISTS tenant_isolation ON field_lifecycle_transitions;

-- USING: قراءة فشل-مغلق (سياق فارغ ⇒ صفر صفوف). WITH CHECK: عزل الكتابة (بلا سياق
-- تُسمح كتابة النظام/الهجرات كما في _sahool_apply_tenant_rls). العزل عبر الأب
-- field_lifecycle.tenant_id (المفتاح الأجنبيّ lifecycle_id).
CREATE POLICY tenant_isolation ON field_lifecycle_transitions
USING (
    EXISTS (
        SELECT 1 FROM field_lifecycle fl
        WHERE fl.lifecycle_id = field_lifecycle_transitions.lifecycle_id
          AND fl.tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    )
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR EXISTS (
        SELECT 1 FROM field_lifecycle fl
        WHERE fl.lifecycle_id = field_lifecycle_transitions.lifecycle_id
          AND fl.tenant_id::TEXT = current_setting('app.current_tenant', true)
    )
);

COMMIT;
