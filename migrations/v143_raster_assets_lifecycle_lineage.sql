-- migrations/v143_raster_assets_lifecycle_lineage.sql
--
-- v143: دورة حياة أصول الراستر + نَسَب هندسة الحقل (تدقيق صور الأقمار 2026-07-05).
--
-- المشكلة (بمراجعة الكود + تقرير الفجوات):
--   ١) raster_assets بلا عمود حالة ⇒ لا تمييز بين أصل «جاهز» و«فاشل» و«بائت» (بعد
--      تعديل هندسة الحقل). القرّاء يعيدون كلّ صفّ كأنّه صالح (FINDING-011).
--   ٢) نَسَب الهندسة مقطوع: field_geometry_history (revision INTEGER، منصّة) غير مربوط
--      بمخرجات raster-service. لا يستطيع الأصل تسجيل مراجعة الهندسة التي أنتجته
--      (FINDING-004) ⇒ لا يمكن إبطال/إعادة معالجة الأصول البائتة بدقّة.
--
-- الحلّ: عمودان جديدان على raster_assets:
--   • asset_status TEXT NOT NULL DEFAULT 'ready' CHECK (pending/ready/stale/failed)
--     — يمكّن عامل الإبطال (v143 كود لاحق) وسمَ 'stale'، والقرّاء تصفية 'failed'.
--   • geometry_revision INTEGER NULL — مراجعة field_geometry_history السارية وقت الإنتاج
--     (تُملأ من مُطلِق المعالجة؛ NULL للأصول القديمة/غير المعروفة — لا اختلاق).
-- + فهرس جزئيّ للاستعلام السريع على الأصول الجاهزة. idempotent + آمن لإعادة التشغيل.
-- لا RLS جديد: raster_assets يحمل سياسة tenant_isolation منذ v14 (إضافة أعمدة فقط).

BEGIN;

ALTER TABLE raster_assets
    ADD COLUMN IF NOT EXISTS asset_status TEXT NOT NULL DEFAULT 'ready';

-- قيد الحالة يُضاف منفصلاً وبحراسة (idempotent): لا نُكرّر القيد إن وُجد.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_raster_assets_status'
    ) THEN
        ALTER TABLE raster_assets
            ADD CONSTRAINT chk_raster_assets_status
            CHECK (asset_status IN ('pending', 'ready', 'stale', 'failed'));
    END IF;
END $$;

ALTER TABLE raster_assets
    ADD COLUMN IF NOT EXISTS geometry_revision INTEGER;

-- استعلام «أحدث أصل جاهز» و«التواريخ المتاحة» يصفّيان الحالة ⇒ فهرس جزئيّ على الجاهز.
CREATE INDEX IF NOT EXISTS idx_raster_assets_ready
ON raster_assets (tenant_id, field_id, index_name, acquisition_date DESC)
WHERE asset_status = 'ready';

-- فهرس للنَّسَب: العثور على أصول مراجعة هندسة بعينها (للإبطال/التدقيق).
CREATE INDEX IF NOT EXISTS idx_raster_assets_geometry_revision
ON raster_assets (tenant_id, field_id, geometry_revision)
WHERE geometry_revision IS NOT NULL;

COMMIT;
