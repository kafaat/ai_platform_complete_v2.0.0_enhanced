-- v95: prescriptions — وصفات المعدّل المتغيّر اليدويّة (FieldView "manual prescriptions")
-- ════════════════════════════════════════════════════════════════════════
-- المشكلة (صدق المصدر): لم يكن في الخادم جدول/نقطة لِحفظ "وصفة معدّل متغيّر"
-- قابلة للقراءة. `core/vrt_manual_maps.py` و`api/prescriptions.py` يولّدان مناطق
-- agronomic في الذاكرة فقط (لا إدامة)، و`useFieldPrescription` في الواجهة قراءةُ
-- تقطيع كمّيّ (quantile) من الراستر — ليست وصفةً محفوظة. هذا الجدول يجعل وصفة
-- **يدويّة** (المستخدِم يرسم المناطق ويضبط المعدّلات) دائمةً وقابلة للقراءة عبر
-- GET /api/v1/fields/{field_id}/prescriptions (نظير FieldView Manual Prescriptions).
--
-- صدق منهجيّ: هذه وصفة **يدويّة** صرفة — لا توليد agronomic آليّ هنا ولا صيغة
-- مُتحكِّم (controller) مُختلقة. كلّ منطقة = هندسة GeoJSON يرسمها المستخدِم + معدّل
-- + وحدة. التصدير (GeoJSON/CSV) يتمّ في الواجهة. صيغ المُتحكِّمات (ISOXML/Shapefile)
-- مؤجّلة كـTODO موثَّق (لا ندّعي ما لا ننتجه فعلاً).
--
-- النموذج يطابق نقطة الحفظ POST حقلاً بحقل: معرّف نصّيّ (idempotency على مستوى
-- العميل، كنمط pin_id) + مستأجِر + حقل + اسم + نوع منتج {seed|fertility} + مناطق
-- JSONB [{geometry GeoJSON, rate, unit}] + مُنشئ + وقت. لا أعمدة مخترَعة.
--
-- العزل: RLS على tenant_id (تفعيل صريح + FORCE + سياسة tenant_isolation على
-- current_setting('app.current_tenant')، fail-closed: سياق فارغ ⇒ صفر صفوف) —
-- نفس نمط v94_scouting_pins / v92_offline_pending_ops حرفيّاً. idempotent بالكامل
-- (IF NOT EXISTS + DROP POLICY IF EXISTS).
CREATE TABLE IF NOT EXISTS prescriptions (
    prescription_id TEXT PRIMARY KEY,                     -- معرّف العميل (idempotency)
    tenant_id       UUID NOT NULL,
    field_id        TEXT NOT NULL,
    name            TEXT NOT NULL,                         -- اسم الوصفة (واجهة)
    product_type    TEXT NOT NULL DEFAULT 'seed',          -- {seed|fertility}
    zones           JSONB NOT NULL DEFAULT '[]'::jsonb,    -- [{geometry GeoJSON, rate, unit}]
    created_by      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- فهرس القراءة الرئيس: وصفات حقلٍ لمستأجِر بترتيب الأحدث أوّلاً (GET endpoint).
CREATE INDEX IF NOT EXISTS idx_prescriptions_tenant_field
    ON prescriptions (tenant_id, field_id, created_at DESC);

-- RLS: تفعيل صريح + FORCE + سياسة العزل (نفس نمط v94/v92 — جدول لاحق للحلقة الشاملة).
-- FORCE يُخضِع حتّى مالك الجدول للسياسة (دفاع عمق). السياسة مُنطّقة بالمستأجِر عبر
-- current_setting('app.current_tenant') (fail-closed: سياق فارغ ⇒ صفر صفوف).
ALTER TABLE prescriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE prescriptions FORCE ROW LEVEL SECURITY;  -- يُخضِع المالك أيضاً

DROP POLICY IF EXISTS tenant_isolation ON prescriptions;  -- idempotency
CREATE POLICY tenant_isolation ON prescriptions
    USING (
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    )
    WITH CHECK (
        -- عزل الكتابة (دفاع عمق): بلا سياق (هجرات/نظام) تُسمح، وإلّا المطابقة فقط.
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

COMMENT ON TABLE prescriptions IS
    'وصفات المعدّل المتغيّر اليدويّة (FieldView Manual Prescriptions) — مناطق يرسمها المستخدِم (geometry GeoJSON) + معدّل/وحدة لكلّ منطقة + اسم + نوع منتج {seed|fertility}؛ قابلة للقراءة عبر GET /api/v1/fields/{field_id}/prescriptions (معزولة بالمستأجِر، RLS). يدويّة صرفة: لا توليد agronomic آليّ ولا صيغة مُتحكِّم.';
