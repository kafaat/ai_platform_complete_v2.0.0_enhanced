-- ════════════════════════════════════════════════════════════
-- SAHOOL — تفويض ملكيّة الحقل (مصدر موثوق لـraster-service)
-- ════════════════════════════════════════════════════════════
-- الفجوة: raster-service يفحص ملكيّة الحقل من ذاكرته (_field_layers) فقط — يضعف
-- بعد إعادة التشغيل، وبلا طبقة مخبّأة، وعند غياب X-Tenant-Id. المصدر الموثوق هو
-- جدول fields (field_id فريد عالميّاً، tenant_id مالكه). لكنّ fields عليه FORCE RLS
-- بلا هروب admin في القراءة، فالدور التطبيقيّ (sahool_app, NOBYPASSRLS) لا يقرأ
-- مالك حقلِ مستأجِرٍ آخر مباشرةً.
--
-- الحلّ: دالّة SECURITY DEFINER تُعيد **المعرّف فقط** (tenant_id) لحقلٍ بمعرّفه.
-- تُنشَأ بهويّة الترحيل (المالك/superuser الذي يتجاوز RLS) فتقرأ المالك الحقيقيّ
-- عبر المستأجرين دون كشف بيانات الحقل. تُمنَح لـsahool_app فقط (REVOKE من PUBLIC).
-- لا تُضعِف عزل fields: لا تُعيد صفوفاً ولا أعمدةً غير المالك.

CREATE OR REPLACE FUNCTION sahool_field_owner_tenant(p_field_id text)
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
    SELECT tenant_id::text FROM fields WHERE field_id = p_field_id
$$;

REVOKE ALL ON FUNCTION sahool_field_owner_tenant(text) FROM PUBLIC;

-- المنح للدور التطبيقيّ المقيّد فقط (إن وُجد — idempotent عبر البيئات).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahool_app') THEN
        GRANT EXECUTE ON FUNCTION sahool_field_owner_tenant(text) TO sahool_app;
    END IF;
END $$;

COMMENT ON FUNCTION sahool_field_owner_tenant(text) IS
    'تفويض raster: مالك (tenant_id) لحقل بمعرّفه. SECURITY DEFINER لتجاوز RLS على fields؛ تُعيد المعرّف فقط لا بيانات الحقل.';
