-- v38: قنوات تسليم التنبيهات — توسعة notification_preferences (v9) بقنوات SMS
-- وواتساب + مُعرّف مستخدم نصّيّ (user_ref) للهويّة المنصّيّة + أرضيّة خطورة دنيا.
-- الفجوة: واجهة إعدادات الإشعارات في هذا السبرنت تعرض بريد/SMS/Push/واتساب، لكن
-- جدول v9 يملك بريد/تلغرام/Push فقط، ويُفهرِس user_id (INTEGER، FK لـusers.id)
-- بينما هويّة المنصّة user_id نصّيّة. نُضيف أعمدة القنوات الناقصة + user_ref TEXT
-- لتخزين/قراءة تفضيلات المستخدم الحاليّ لكلّ مستأجِر (UPSERT). idempotent.
-- يعدّل notification_preferences (v9). لا يكسر الأعمدة/الـRLS القائمة.

-- ── قنوات جديدة: SMS + واتساب (مرآة بريد/Push القائمة) ──────────────
ALTER TABLE notification_preferences
    ADD COLUMN IF NOT EXISTS sms_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE notification_preferences
    ADD COLUMN IF NOT EXISTS sms_number VARCHAR(32);
ALTER TABLE notification_preferences
    ADD COLUMN IF NOT EXISTS whatsapp_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE notification_preferences
    ADD COLUMN IF NOT EXISTS whatsapp_number VARCHAR(32);

-- ── أرضيّة خطورة دنيا عامّة للمستخدم (info/warning/critical أو NULL) ──
-- تُطبَّق فوق أرضيّة القناة الافتراضيّة في api.alert_delivery. NULL ⇒ أرضيّة
-- القناة فقط. مُقيَّدة بالقيم المعروفة (تطابق _ALERT_SEVERITIES في main.py).
ALTER TABLE notification_preferences
    ADD COLUMN IF NOT EXISTS min_severity VARCHAR(16);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'notif_pref_min_severity_chk'
    ) THEN
        ALTER TABLE notification_preferences
            ADD CONSTRAINT notif_pref_min_severity_chk
            CHECK (min_severity IS NULL
                   OR min_severity IN ('info', 'warning', 'critical'));
    END IF;
END $$;

-- ── user_ref: هويّة المستخدم النصّيّة (app.current_user_id) ──────────
-- user_id الأصليّ INTEGER (FK لـusers.id) لا يطابق هويّة المنصّة النصّيّة؛
-- النواة تقرأ/تكتب صفّ المستخدم الحاليّ عبر (tenant_id, user_ref). فريد لكلّ
-- (مستأجِر، مستخدم) لدعم UPSERT آمن tenant-isolated.
ALTER TABLE notification_preferences
    ADD COLUMN IF NOT EXISTS user_ref TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_notif_pref_tenant_userref
    ON notification_preferences(tenant_id, user_ref)
    WHERE user_ref IS NOT NULL;
