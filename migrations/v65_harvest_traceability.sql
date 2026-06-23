-- SAHOOL v65 — migrations/v65_harvest_traceability.sql
-- تتبّع سلسلة الإمداد من المزرعة إلى السوق (farm-to-market traceability) — MVP.
--
-- الفجوة (من التحليل التنافسيّ): سهول لديها input-traceability (تتبّع مدخلات على
-- مستوى الحقل) فقط، لا سلسلة حيازة من الحصاد إلى البيع كما لدى xFarm/Farmonaut/Cropin.
-- هذا يسدّ النواة: دفعة حصاد (harvest_lots) + سلسلة حيازة append-only
-- (custody_chain_events) تربط الحصاد→التخزين→النقل→البيع، قابلة للتدقيق.
--
-- يركّب القائم بلا تكرار: field_id/season_id يربطان بـfields/seasons؛ المساحة
-- (area_ha) والغلّة المتوقّعة تُجلبان من fields/recommendation_outcomes عند الحاجة
-- (لا تُخزَّن هنا). الشهادات الرسميّة (GlobalGAP موقَّعة) خارج هذا الـMVP.
--
-- idempotent (IF NOT EXISTS) + RLS صريح لكلّ مستأجِر (نمط v50 soil_lab_tests).

BEGIN;

-- ① دفعة الحصاد — وحدة التتبّع من الحقل إلى السوق.
CREATE TABLE IF NOT EXISTS harvest_lots (
    harvest_lot_id  VARCHAR(50)  PRIMARY KEY,
    tenant_id       UUID         NOT NULL,
    field_id        VARCHAR(50)  NOT NULL REFERENCES fields(field_id) ON DELETE CASCADE,
    -- الموسم اختياريّ ويُفصَل عند حذفه (الدفعة تبقى للتتبّع التاريخيّ).
    season_id       VARCHAR(50)  REFERENCES seasons(season_id) ON DELETE SET NULL,
    crop            VARCHAR(50),                                  -- المحصول (من الموسم أو تجاوز)
    harvest_date    DATE         NOT NULL,                        -- تاريخ الحصاد الفعليّ
    quantity_kg     NUMERIC(12, 2) NOT NULL CHECK (quantity_kg >= 0),
    moisture_pct    NUMERIC(5, 2),                               -- الرطوبة بعد التجفيف
    quality_grade   VARCHAR(10)  CHECK (quality_grade IN ('A', 'B', 'C', 'reject')),
    notes_ar        TEXT,
    -- حالة الدفعة عبر السلسلة (يحرّكها تسجيل أحداث الحيازة تطبيقيّاً).
    status          VARCHAR(20)  NOT NULL DEFAULT 'harvested'
        CHECK (status IN ('harvested', 'stored', 'in_transit', 'at_market', 'sold', 'rejected')),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_harvest_lots_field  ON harvest_lots (field_id);
CREATE INDEX IF NOT EXISTS idx_harvest_lots_season ON harvest_lots (season_id);
CREATE INDEX IF NOT EXISTS idx_harvest_lots_tenant ON harvest_lots (tenant_id, harvest_date DESC);

DROP TRIGGER IF EXISTS trg_harvest_lots_updated_at ON harvest_lots;
CREATE OR REPLACE TRIGGER trg_harvest_lots_updated_at
    BEFORE UPDATE ON harvest_lots
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ② سلسلة الحيازة — سجلّ append-only لكلّ انتقال (حصاد→تخزين→فحص→نقل→بيع).
--    لا trigger updated_at: السجلّ غير قابل للتعديل (محاسبة/تدقيق). content_hash
--    (SHA-256 يحسبه التطبيق) يكشف أيّ تلاعب لاحق بمحتوى الحدث.
CREATE TABLE IF NOT EXISTS custody_chain_events (
    custody_event_id  BIGSERIAL    PRIMARY KEY,
    tenant_id         UUID         NOT NULL,
    harvest_lot_id    VARCHAR(50)  NOT NULL REFERENCES harvest_lots(harvest_lot_id) ON DELETE CASCADE,
    event_type        VARCHAR(30)  NOT NULL
        CHECK (event_type IN ('harvest', 'storage', 'quality_check', 'transport', 'sales')),
    handler           VARCHAR(120),                              -- اسم/معرّف المناوِل
    handler_role      VARCHAR(30)
        CHECK (handler_role IN ('farmer', 'storage', 'transporter', 'trader', 'buyer', 'inspector', 'system')),
    location_name     VARCHAR(120),
    quantity_kg       NUMERIC(12, 2) CHECK (quantity_kg IS NULL OR quantity_kg >= 0),
    event_details     JSONB        NOT NULL DEFAULT '{}'::jsonb, -- تفاصيل مرنة حسب النوع
    occurred_at       TIMESTAMPTZ  NOT NULL,                     -- زمن الحدث الفعليّ
    recorded_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),       -- زمن التسجيل
    content_hash      VARCHAR(64),                               -- SHA-256 لسلامة الحدث
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_custody_events_lot    ON custody_chain_events (harvest_lot_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_custody_events_tenant ON custody_chain_events (tenant_id, recorded_at DESC);

-- ③ RLS صريح لكلّ مستأجِر (نمط v50): ENABLE + FORCE + سياسة tenant_isolation.
--    FORCE صراحةً لأنّ هذين الجدولين يُنشآن بعد v9_rls_force_all في MANIFEST.
ALTER TABLE harvest_lots ENABLE ROW LEVEL SECURITY;
ALTER TABLE harvest_lots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON harvest_lots;
CREATE POLICY tenant_isolation ON harvest_lots
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', TRUE), ''));

ALTER TABLE custody_chain_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE custody_chain_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON custody_chain_events;
CREATE POLICY tenant_isolation ON custody_chain_events
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', TRUE), ''));

COMMENT ON TABLE harvest_lots IS
    'دفعات الحصاد — وحدة تتبّع المحصول من الحقل إلى السوق. تربط field/season. v65.';
COMMENT ON TABLE custody_chain_events IS
    'سلسلة الحيازة append-only (حصاد→تخزين→فحص→نقل→بيع) مع content_hash للتدقيق. v65.';

COMMIT;
