-- ════════════════════════════════════════════════════════════
-- SAHOOL v23 — إدارة المعدّات (Equipment): معدّات + صيانة/أعطال
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة (تدقيق التغطية، الطبقة ١١ — غائبة 100%): جرّارات/مضخّات/
-- حصّادات مع ساعات التشغيل والصيانة الدوريّة والأعطال. لم يكن لها أيّ جدول
-- (EquipmentInput في الكود كان مُدخَل حساب رشّ فقط، لا إدارة معدّات).
--
-- النموذج: معدّة ← سجلّات صيانة (مجدولة/إصلاح/عطل). العزل: RLS لكلّ مستأجر.

-- ── equipment: المعدّة + حالتها + ساعات تشغيلها ───────────────
CREATE TABLE IF NOT EXISTS equipment (
    equipment_id    VARCHAR(50)  PRIMARY KEY,
    tenant_id       UUID         NOT NULL,
    name            VARCHAR(120) NOT NULL,
    type            VARCHAR(30)  NOT NULL
        CHECK (type IN ('tractor', 'pump', 'harvester', 'sprayer', 'other')),
    status          VARCHAR(20)  NOT NULL DEFAULT 'operational'
        CHECK (status IN ('operational', 'maintenance', 'broken', 'retired')),
    operating_hours NUMERIC(12, 1) NOT NULL DEFAULT 0 CHECK (operating_hours >= 0),
    purchase_date   DATE,
    notes           TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_equipment_tenant ON equipment(tenant_id, type);

DROP TRIGGER IF EXISTS trg_equipment_updated_at ON equipment;
CREATE OR REPLACE TRIGGER trg_equipment_updated_at
    BEFORE UPDATE ON equipment
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── equipment_maintenance: صيانة دوريّة / إصلاح / عطل ─────────
CREATE TABLE IF NOT EXISTS equipment_maintenance (
    maintenance_id VARCHAR(50)  PRIMARY KEY,
    tenant_id      UUID         NOT NULL,
    equipment_id   VARCHAR(50)  NOT NULL REFERENCES equipment(equipment_id) ON DELETE CASCADE,
    kind           VARCHAR(20)  NOT NULL
        CHECK (kind IN ('scheduled', 'repair', 'breakdown', 'inspection')),
    status         VARCHAR(20)  NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'done', 'cancelled')),
    scheduled_date DATE,
    performed_date DATE,
    cost_usd       NUMERIC(12, 2),
    notes          TEXT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_equip_maint_equip
    ON equipment_maintenance(equipment_id, scheduled_date);

DROP TRIGGER IF EXISTS trg_equip_maint_updated_at ON equipment_maintenance;
CREATE OR REPLACE TRIGGER trg_equip_maint_updated_at
    BEFORE UPDATE ON equipment_maintenance
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- عزل المستأجرين (self-applied بعد force_all)
SELECT _sahool_apply_tenant_rls('equipment');
SELECT _sahool_apply_tenant_rls('equipment_maintenance');

COMMENT ON TABLE equipment             IS 'المعدّات (جرّار/مضخّة/حصّادة) + ساعات التشغيل والحالة. v23.';
COMMENT ON TABLE equipment_maintenance IS 'سجلّ الصيانة/الأعطال للمعدّات. v23.';
