-- v214 (H5.1): ربط الحقل بمصدر ماء الريّ خادميّاً — جدول وصل يجعل مصدر الماء
-- «مُشتقّاً من الخادم» لا «مُدخَلاً من العميل». يغلق تجاوزَين في بوّابة الملوحة H5:
--   (1) العميل كان يُمرّر water_source_id حرّاً (أو يحذفه ليتجاوز البوّابة) — الآن
--       الخادم يحلّ المصدر النشِط من هذا الجدول، ولا يثق بقيمة العميل.
--   (2) يدعم تعدّد المصادر والتغيّر الزمنيّ والخلط دون إعادة تصميم (أولويّة + نسبة خلط
--       + نافذة صلاحيّة + حالة)، فبوّابة الملوحة تُقيَّم على كلّ مصدر نشِط (fail-closed
--       على الأسوأ).
-- بلا PostGIS. field_id نصّ (يطابق fields.field_id VARCHAR(50)) بلا FK — على نمط جداول
-- الريّ الأخرى (v179/v185). RLS صارم (ENABLE+FORCE+WITH CHECK) على app.current_tenant.
BEGIN;

CREATE TABLE IF NOT EXISTS field_irrigation_source_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    water_source_id UUID NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,
    priority INTEGER NOT NULL DEFAULT 1 CHECK (priority >= 1),
    mixing_ratio NUMERIC CHECK (mixing_ratio IS NULL OR (mixing_ratio >= 0 AND mixing_ratio <= 1)),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','retired')),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    UNIQUE (id, tenant_id),
    FOREIGN KEY (water_source_id, tenant_id)
        REFERENCES irrigation_water_sources(id, tenant_id) ON DELETE CASCADE
);

-- حلّ المصدر النشِط لحقل عند لحظة معيّنة (status='active' + النافذة تغطّي now)، مُرتَّباً
-- بالأولويّة — الفهرس الجزئيّ يخدم استعلام الحلّ في المسار الساخن.
CREATE INDEX IF NOT EXISTS idx_fisa_active_field
    ON field_irrigation_source_assignments (tenant_id, field_id, priority)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_fisa_source
    ON field_irrigation_source_assignments (tenant_id, water_source_id);

-- RLS: عزل صارم بالمستأجِر (نمط v170). الكتابة تفشل مُغلَقة بلا app.current_tenant.
ALTER TABLE field_irrigation_source_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_irrigation_source_assignments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON field_irrigation_source_assignments;
CREATE POLICY tenant_isolation ON field_irrigation_source_assignments
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''));

COMMENT ON TABLE field_irrigation_source_assignments IS
    'H5.1 server-authoritative field↔water-source binding (validity window, priority, mixing) — the salinity gate resolves the source from here, never from client input.';
COMMENT ON COLUMN field_irrigation_source_assignments.priority IS
    'Lower = primary. The salinity gate evaluates every active source and fails closed on the worst.';
COMMENT ON COLUMN field_irrigation_source_assignments.mixing_ratio IS
    'Optional 0..1 blend fraction; NULL = sole/undeclared. Advisory for now — the gate blocks if ANY active source blocks regardless of ratio.';

COMMIT;
