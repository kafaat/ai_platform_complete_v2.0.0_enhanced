-- migrations/v81_actuator_command_dedup.sql
--
-- مخزن إزالة التكرار العنقوديّ للـactuator (تصليب الأنظمة الموزّعة، PR #393):
-- حارس التكرار في actuator-service كان dict داخل العمليّة (per-replica) — مع عدّة نُسَخ
-- أو إعادة تسليم MQTT أو إعادة تشغيل قد يُطلَق الأمر مرّةً لكلّ نسخة ⇒ **تنفيذ مزدوج على
-- مضخّة/صمّام**. هذا الجدول يجعل الـdedup **عنقوديّاً (cluster-safe)**: فحص-وتثبيت ذرّيّ
-- عبر القاعدة (INSERT … ON CONFLICT … WHERE last_fired_at < now()-window) — المخزن
-- المشترك الدائم هو السلطة، لا ذاكرة محلّيّة. يُستهلَك خلف علم ACTUATOR_IDEMPOTENCY_MODE
-- (الإغلاق المرن: local→shadow→cluster) فلا يكسر السلوك الحاليّ.
--
--   • dedup_key PRIMARY KEY = "tenant:field:device:command" (المفتاح الفعّال).
--   • tenant_id UUID NOT NULL ⇒ عزل المستأجِر عبر RLS+FORCE بسياسة current_setting
--     (الـactuator يضبط app.current_tenant قبل الاستعلام؛ يتّصل بـsahool_app NOBYPASSRLS).
--   • صفّ واحد لكلّ أمر فعّال (upsert على last_fired_at) — جدول صغير، يُنظَّف ضمنيّاً بالكتابة.
-- idempotent (CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS قبل CREATE POLICY).

BEGIN;

CREATE TABLE IF NOT EXISTS actuator_command_dedup (
    dedup_key       TEXT         PRIMARY KEY,            -- tenant:field:device:command
    tenant_id       UUID         NOT NULL,               -- عزل المستأجر (RLS أدناه)
    last_fired_at   TIMESTAMPTZ  NOT NULL DEFAULT now()  -- آخر إطلاق فعليّ (نافذة التهدئة)
);

CREATE INDEX IF NOT EXISTS idx_actuator_command_dedup_tenant
    ON actuator_command_dedup (tenant_id);

COMMENT ON TABLE  actuator_command_dedup IS
    'مخزن إزالة التكرار العنقوديّ للأوامر (cluster-safe، يمنع التنفيذ المزدوج). tenant-isolated عبر RLS. v81.';
COMMENT ON COLUMN actuator_command_dedup.dedup_key     IS 'المفتاح الفعّال: tenant:field:device:command.';
COMMENT ON COLUMN actuator_command_dedup.last_fired_at IS 'آخر إطلاق — فحص-وتثبيت ذرّيّ ضدّ نافذة التهدئة.';

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
ALTER TABLE actuator_command_dedup ENABLE ROW LEVEL SECURITY;
ALTER TABLE actuator_command_dedup FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON actuator_command_dedup;
CREATE POLICY tenant_isolation ON actuator_command_dedup
USING (
    tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR tenant_id::TEXT = current_setting('app.current_tenant', true)
);

COMMIT;
