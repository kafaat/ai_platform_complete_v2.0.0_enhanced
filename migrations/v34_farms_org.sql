-- ════════════════════════════════════════════════════════════
-- SAHOOL v34 — تنظيم المزرعة (Farm organization) — حقول إضافيّة
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة (Sprint 1b — تأسيس المزرعة): شاشة «إنشاء مزرعة» تجمع بيانات
-- تنظيميّة (الدولة/المنطقة/المنطقة الزمنيّة/نظام الوحدات/العملة/الوصف/نوع النشاط)
-- لم يكن جدول farms (v19) يخزّنها. نضيفها هنا حقولاً اختياريّة (idempotent) — لا
-- تكسر صفّاً قائماً، والعزل (RLS) المُطبَّق في v19 يبقى ساريّاً.

ALTER TABLE farms ADD COLUMN IF NOT EXISTS country       VARCHAR(60);
ALTER TABLE farms ADD COLUMN IF NOT EXISTS region        VARCHAR(80);
ALTER TABLE farms ADD COLUMN IF NOT EXISTS timezone      VARCHAR(40);
ALTER TABLE farms ADD COLUMN IF NOT EXISTS units         VARCHAR(10) DEFAULT 'metric';
ALTER TABLE farms ADD COLUMN IF NOT EXISTS currency      VARCHAR(10);
ALTER TABLE farms ADD COLUMN IF NOT EXISTS description   TEXT;
ALTER TABLE farms ADD COLUMN IF NOT EXISTS activity_type VARCHAR(40);
