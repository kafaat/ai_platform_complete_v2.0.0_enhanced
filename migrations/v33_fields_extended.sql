-- v33: إثراء جدول الحقول — كود الحقل + مصدر الماء + الملكيّة + الدولة/الإقليم
-- الفجوة: نموذج «إضافة حقل» صار يجمع كود الحقل ومصدر الماء، والنظام يكشف آليّاً
-- الدولة + الإقليم (المحافظة) من مركز المضلّع المرسوم؛ لا أعمدة تحفظها. idempotent.
-- يعدّل fields (v9). الكشف الآلي عبر _reverse_geocode (geo_zone_locator + YEMEN_BBOX).

ALTER TABLE fields ADD COLUMN IF NOT EXISTS field_code VARCHAR(50);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE fields ADD COLUMN IF NOT EXISTS water_source VARCHAR(20);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS ownership_type VARCHAR(20);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS country VARCHAR(60);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS region VARCHAR(80);
