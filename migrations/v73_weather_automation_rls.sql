-- migrations/v73_weather_automation_rls.sql
--
-- HIGH-002 (شهادة الإنتاج): weather_automation_locations/cache بلا RLS ⇒ sahool_app
-- يقرأ صفوف كلّ المستأجرين. لا عمود tenant_id فيهما (يُعزَلان عبر field_id → fields).
--
-- يُمكَّن الآن لأنّ مجدوِل الطقس (load_from_db/refresh_all) صار على مسبح المهامّ (دور
-- sahool_jobs، BYPASSRLS) ⇒ يقرأ عابراً للمستأجرين كما يتطلّب، بينما **التطبيق**
-- (sahool_app) يقرأ طقس حقله فقط بسياق المستأجِر.
--
-- locations: مرئيّ إن كان عالميّاً (field_id IS NULL) أو يخصّ حقل المستأجِر الحاليّ.
-- cache: يرث رؤية موقعه (location_key ضمن المواقع المرئيّة) — فيُعزَل تلقائيّاً دون
-- تكرار سلسلة fields. (مفتاحه إحداثيّة عامّة + طقس عامّ؛ الحسّاسيّة في ربط الحقل،
-- وهو محكوم بسياسة locations.)

BEGIN;

-- ١) weather_automation_locations: عزل عبر field_id → fields.tenant_id (NULL=عالميّ)
ALTER TABLE weather_automation_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE weather_automation_locations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON weather_automation_locations;
CREATE POLICY tenant_isolation ON weather_automation_locations
USING (
    field_id IS NULL
    OR EXISTS (
        SELECT 1 FROM fields f
        WHERE f.field_id = weather_automation_locations.field_id
          AND f.tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    )
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR field_id IS NULL
    OR EXISTS (
        SELECT 1 FROM fields f
        WHERE f.field_id = weather_automation_locations.field_id
          AND f.tenant_id::TEXT = current_setting('app.current_tenant', true)
    )
);

-- ٢) weather_automation_cache: يرث رؤية موقعه (السطر المرجعيّ في locations مرئيّ).
-- subquery يخضع لـRLS على locations ⇒ يُرجِع المواقع المرئيّة للسياق فقط.
ALTER TABLE weather_automation_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE weather_automation_cache FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON weather_automation_cache;
CREATE POLICY tenant_isolation ON weather_automation_cache
USING (
    location_key IN (SELECT location_key FROM weather_automation_locations)
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR location_key IN (SELECT location_key FROM weather_automation_locations)
);

COMMIT;
