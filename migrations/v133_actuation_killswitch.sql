-- v133: actuation_killswitch — مفتاح إيقاف طوارئ التشغيل (fail-closed) بنطاق مستأجِر/حقل/صمّام
-- ════════════════════════════════════════════════════════════════════════
-- المشكلة (سطر v29.5-op-1): لا يملك SAHOOL «مفتاح إيقاف طوارئ» يوقف التشغيل الفيزيائيّ
-- فوراً بنطاق مُحدَّد. الموجود مختلف: إزالة تكرار الأوامر (v67)، سجلّ التنفيذ (v68)،
-- متغيّر البيئة ACTUATOR_MODE، تفعيل القاعدة الفرديّة automation_rules.enabled، و
-- break_glass (v90) — لا شيء منها «إيقاف طوارئ آنيّ» قابل للنطق (مستأجِر/حقل/صمّام).
--
-- النموذج (fail-closed): صفّ لكلّ مفتاح إيقاف مُشتبَك. scope يحدّد اتّساع التوقّف:
--   • tenant — يوقف كلّ تشغيل هذا المستأجِر (field_id/valve_id NULL).
--   • field  — يوقف الحقل المُحدَّد فقط (field_id مُعيَّن).
--   • valve  — يوقف الصمّام/الجهاز المُحدَّد فقط (valve_id مُعيَّن).
-- المستشير (shared/actuation_killswitch.py) يُطابق قبل أيّ send_mqtt_command/إدراج طابور:
-- أيّ مفتاح فعّال (active) غير منتهٍ (expires_at) مُطابِق ⇒ التشغيل مُوقَف. تعذّر القاعدة ⇒
-- مُوقَف (fail-closed، تماثُل مع idiom الخدمة). لا اختراع أرقام — تخزين نيّة إيقاف صريحة.
--
-- العزل: RLS على tenant_id (تفعيل صريح + FORCE + سياسة tenant_isolation على
-- current_setting('app.current_tenant')، fail-closed: سياق فارغ ⇒ صفر صفوف) — نفس نمط
-- v98_water_ledger حرفيّاً. idempotent بالكامل (IF NOT EXISTS + DROP POLICY IF EXISTS).

BEGIN;

CREATE TABLE IF NOT EXISTS actuation_killswitch (
    id           UUID         NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,  -- معرّف المفتاح
    tenant_id    UUID         NOT NULL,                                         -- عزل المستأجِر (RLS أدناه)
    scope        TEXT         NOT NULL CHECK (scope IN ('tenant', 'field', 'valve')),  -- اتّساع التوقّف
    field_id     TEXT,                                                          -- الحقل (نطاق field) — NULL لغيره
    valve_id     TEXT,                                                          -- الصمّام/الجهاز (نطاق valve) — NULL لغيره
    active       BOOLEAN      NOT NULL DEFAULT TRUE,                            -- مُشتبَك؟ (فكّه = active=false)
    reason       TEXT         NOT NULL,                                         -- سبب الإيقاف (إلزاميّ — لا إيقاف صامت)
    engaged_by   TEXT,                                                          -- من اشتبك المفتاح (أثر)
    engaged_at   TIMESTAMPTZ  DEFAULT now(),                                    -- لحظة الاشتباك
    expires_at   TIMESTAMPTZ                                                    -- انتهاء تلقائيّ (NULL = دائم حتّى الفكّ)
);

-- فهرس القراءة الحرِج: يُستشار في المسار الساخن (قبل كلّ أمر) — مفاتيح مستأجِر الفعّالة فقط.
CREATE INDEX IF NOT EXISTS idx_actuation_killswitch_active
    ON actuation_killswitch (tenant_id, scope, field_id, valve_id)
    WHERE active;

COMMENT ON TABLE  actuation_killswitch IS
    'مفتاح إيقاف طوارئ التشغيل (fail-closed) بنطاق مستأجِر/حقل/صمّام — يوقف send_mqtt_command/إدراج الطابور فوراً. تخزين نيّة إيقاف صريحة (reason إلزاميّ)؛ تعذّر القاعدة ⇒ مُوقَف. معزول بالمستأجِر (RLS). v133.';
COMMENT ON COLUMN actuation_killswitch.scope IS
    'tenant=يوقف كلّ المستأجِر · field=الحقل (field_id) · valve=الصمّام (valve_id).';
COMMENT ON COLUMN actuation_killswitch.expires_at IS 'انتهاء تلقائيّ إن حُدِّد، وإلّا NULL (دائم حتّى الفكّ اليدويّ).';

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
-- FORCE يُخضِع حتّى مالك الجدول للسياسة (دفاع عمق). السياسة مُنطّقة بالمستأجِر عبر
-- current_setting('app.current_tenant') (fail-closed: سياق فارغ ⇒ صفر صفوف).
ALTER TABLE actuation_killswitch ENABLE ROW LEVEL SECURITY;
ALTER TABLE actuation_killswitch FORCE ROW LEVEL SECURITY;  -- يُخضِع المالك أيضاً

DROP POLICY IF EXISTS tenant_isolation ON actuation_killswitch;  -- idempotency
CREATE POLICY tenant_isolation ON actuation_killswitch
    USING (
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    )
    WITH CHECK (
        -- عزل الكتابة (دفاع عمق): بلا سياق (هجرات/نظام) تُسمح، وإلّا المطابقة فقط.
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

COMMIT;
