-- v98: water_ledger — دفتر المياه اليوميّ المُخزَّن القابل للتدقيق (إلهام IrriPro / FAO-56)
-- ════════════════════════════════════════════════════════════════════════
-- المشكلة (الفجوة #1 في sahool-brain/decisions/water-intelligence-direction.md):
-- SAHOOL يملك نواة ريّ شبه كاملة (FAO-56 ET0/Kc/ETc + توازن مائيّ + هيدروليك +
-- سيناريو + تفسير + كلفة)، لكنّ قرار الريّ يُحسَب ويُعرَض ويُنسى — **لا دفتر يوميّ
-- مُسجَّل/مُدقَّق** يربط كلّ يوم بقيمه (ET0/Kc/ETc/مطر/ريّ/رطوبة/عجز/مرحلة/قرار/ثقة).
-- هذا الجدول يُدِيم «دفتر مياه يوميّ» لكلّ حقل فيجعل قرار الريّ قابلاً للتدقيق والتكرار.
--
-- صدق منهجيّ صارم (نمط v78_decision_record): هذا **تخزين/تدقيق** لقيم تُمرَّر من
-- المستدعي (أو محسوبة بمحرّكات FAO-56 القائمة core/engines/) — لا اختراع أرقام.
-- الحقول الناقصة ⇒ NULL (لا تلفيق). لا تُعاد بناء نواة الريّ (موجودة) هنا.
--
-- النموذج: صفّ لكلّ (حقل، يوم) — field_id نصّ (نمط v95) + tenant_id للعزل +
-- ledger_date (التاريخ) + قيم المياه اليوميّة (كلّها nullable عدا المفاتيح). القيد
-- الفريد على (field_id, ledger_date) يجعل الـupsert idempotent (ON CONFLICT … DO UPDATE).
--
-- العزل: RLS على tenant_id (تفعيل صريح + FORCE + سياسة tenant_isolation على
-- current_setting('app.current_tenant')، fail-closed: سياق فارغ ⇒ صفر صفوف) —
-- نفس نمط v95_prescriptions / v78_decision_record حرفيّاً. idempotent بالكامل
-- (IF NOT EXISTS + DROP POLICY IF EXISTS).

BEGIN;

CREATE TABLE IF NOT EXISTS water_ledger (
    ledger_id         UUID         NOT NULL DEFAULT gen_random_uuid(),  -- معرّف بديل
    tenant_id         UUID         NOT NULL,                            -- عزل المستأجِر (RLS أدناه)
    field_id          TEXT         NOT NULL,                            -- الحقل (نمط v95: نصّ)
    ledger_date       DATE         NOT NULL,                            -- يوم الدفتر (التدقيق)
    et0_mm            DOUBLE PRECISION,                                 -- التبخّر-نتح المرجعيّ (FAO-56) — NULL إن غاب
    kc                DOUBLE PRECISION,                                 -- معامل المحصول (FAO-56) — NULL إن غاب
    etc_mm            DOUBLE PRECISION,                                 -- ETc = ET0×Kc — NULL إن غاب
    rain_mm           DOUBLE PRECISION,                                 -- المطر اليوميّ — NULL إن غاب
    irrigation_mm     DOUBLE PRECISION,                                 -- ماء الريّ المُطبَّق — NULL إن غاب
    soil_moisture_pct DOUBLE PRECISION,                                 -- رطوبة التربة % — NULL إن غاب
    depletion_mm      DOUBLE PRECISION,                                 -- نضوب منطقة الجذور — NULL إن غاب
    deficit_mm        DOUBLE PRECISION,                                 -- العجز المائيّ — NULL إن غاب
    stage             TEXT,                                             -- المرحلة الفينولوجيّة — NULL إن غاب
    decision          TEXT,                                             -- قرار الريّ (نصّ) — NULL إن غاب
    confidence        DOUBLE PRECISION,                                 -- ثقة القرار — NULL إن غاب (لا تلفيق)
    created_by        TEXT,                                             -- من سجّل/حسب القيد
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    -- المفتاح الأساس مركّب لِيضمن idempotency الـupsert اليوميّ (حقل×يوم فريد).
    PRIMARY KEY (field_id, ledger_date)
);

-- فهرس القراءة الرئيس: دفتر حقلٍ لمستأجِر بترتيب التاريخ (GET endpoint ?from=&to=).
CREATE INDEX IF NOT EXISTS idx_water_ledger_tenant_field
    ON water_ledger (tenant_id, field_id, ledger_date);

COMMENT ON TABLE  water_ledger IS
    'دفتر المياه اليوميّ المُخزَّن القابل للتدقيق (إلهام IrriPro / FAO-56) — صفّ لكلّ (حقل، يوم): ET0/Kc/ETc/مطر/ريّ/رطوبة/عجز/مرحلة/قرار/ثقة. تخزين/تدقيق لقيم تُمرَّر من المستدعي أو محسوبة بمحرّكات FAO-56 القائمة — لا اختراع أرقام، الناقص NULL. معزول بالمستأجِر (RLS). v98.';
COMMENT ON COLUMN water_ledger.confidence IS 'ثقة القرار إن توفّرت، وإلا NULL (لا تلفيق).';

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
-- FORCE يُخضِع حتّى مالك الجدول للسياسة (دفاع عمق). السياسة مُنطّقة بالمستأجِر عبر
-- current_setting('app.current_tenant') (fail-closed: سياق فارغ ⇒ صفر صفوف).
ALTER TABLE water_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE water_ledger FORCE ROW LEVEL SECURITY;  -- يُخضِع المالك أيضاً

DROP POLICY IF EXISTS tenant_isolation ON water_ledger;  -- idempotency
CREATE POLICY tenant_isolation ON water_ledger
    USING (
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    )
    WITH CHECK (
        -- عزل الكتابة (دفاع عمق): بلا سياق (هجرات/نظام) تُسمح، وإلّا المطابقة فقط.
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

COMMIT;
