-- v94: persistent scouting pins (FieldView-style) — جدول دبابيس المشاهدات الميدانيّة
-- ════════════════════════════════════════════════════════════════════════
-- المشكلة (صدق المصدر): نقطة POST /api/v1/fields/{field_id}/pins كانت تتحقّق من
-- المشاهدة وتُرجِعها مُطبَّعة فقط (الحفظ كان على الموبايل offline-first) — لا جدول
-- قابل للقراءة في الخادم. لذا الواجهة أبقت الدبابيس محلّيّة للجلسة (تختفي بإعادة
-- التحميل) مع شارة «session-only» صريحة. هذا الجدول يجعلها دائمة وقابلة للقراءة عبر
-- GET /api/v1/scouting/pins?field_id=… (نظير FieldView Scouting Pins).
--
-- النموذج يطابق dataclass ScoutingPin في api/scouting_pins.py حقلاً بحقل:
-- موقع GPS + فئة مشكلة (taxonomy يمنيّة) + شدّة + حالة + علم موسمي/دائم + ملاحظة
-- عربيّة + صورة + لون عرض. لا أعمدة مخترَعة.
--
-- العزل: RLS على tenant_id عبر نفس نمط v92_offline_pending_ops / v89_invitations
-- (تفعيل صريح + FORCE + سياسة tenant_isolation على current_setting('app.current_tenant')،
-- fail-closed: سياق فارغ ⇒ صفر صفوف). جدول لاحق للحلقات الشاملة (v9/v70) فيلزمه RLS
-- صريحاً هنا. idempotent بالكامل (IF NOT EXISTS + DROP POLICY IF EXISTS).
CREATE TABLE IF NOT EXISTS scouting_pins (
    pin_id         TEXT PRIMARY KEY,                      -- معرّف العميل (idempotency)
    tenant_id      UUID NOT NULL,
    field_id       TEXT NOT NULL,
    lat            DOUBLE PRECISION NOT NULL,
    lng            DOUBLE PRECISION NOT NULL,
    issue_category TEXT NOT NULL,                         -- IssueCategory value
    severity       TEXT NOT NULL DEFAULT 'medium',        -- Severity value
    status         TEXT NOT NULL DEFAULT 'new',           -- PinStatus value
    persistence    TEXT NOT NULL DEFAULT 'seasonal',      -- Persistence (seasonal|permanent)
    crop           TEXT,
    issue_code     TEXT,                                  -- من الـtaxonomy (مثل tomato.tuta)
    note_ar        TEXT,
    photo_uri      TEXT,                                  -- مسار دائم من mediaStore
    color          TEXT,                                  -- ترميز لوني (واجهة)
    created_by     TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- فهرس القراءة الرئيس: دبابيس حقلٍ لمستأجِر بترتيب الأحدث أوّلاً (GET endpoint).
CREATE INDEX IF NOT EXISTS idx_scouting_pins_tenant_field
    ON scouting_pins (tenant_id, field_id, created_at DESC);

-- RLS: تفعيل صريح + FORCE + سياسة العزل (نفس نمط v92/v89 — جدول لاحق للحلقة الشاملة).
-- FORCE يُخضِع حتّى مالك الجدول للسياسة (دفاع عمق). السياسة مُنطّقة بالمستأجِر عبر
-- current_setting('app.current_tenant') (fail-closed: سياق فارغ ⇒ صفر صفوف).
ALTER TABLE scouting_pins ENABLE ROW LEVEL SECURITY;
ALTER TABLE scouting_pins FORCE ROW LEVEL SECURITY;  -- يُخضِع المالك أيضاً

DROP POLICY IF EXISTS tenant_isolation ON scouting_pins;  -- idempotency
CREATE POLICY tenant_isolation ON scouting_pins
    USING (
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    )
    WITH CHECK (
        -- عزل الكتابة (دفاع عمق): بلا سياق (هجرات/نظام) تُسمح، وإلّا المطابقة فقط.
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

COMMENT ON TABLE scouting_pins IS
    'دبابيس المشاهدات الميدانيّة الدائمة (FieldView Scouting Pins) — موقع GPS + فئة/شدّة/حالة + علم موسمي/دائم + ملاحظة؛ قابلة للقراءة عبر GET /api/v1/scouting/pins?field_id=…';
