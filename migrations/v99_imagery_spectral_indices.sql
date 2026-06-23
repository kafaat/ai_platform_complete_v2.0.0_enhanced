-- migrations/v99_imagery_spectral_indices.sql
-- Bundle D / D2b: مؤشّرات الإجهاد المائيّ الطيفيّة (NDMI + MSI) لكلّ حقل.
--
-- يوسّع imagery_automation_fields (نظير NDVI في v54) لتخزين آخر متوسّط NDMI/MSI
-- محسوب + تاريخه. خطّ أتمتة الصور (imagery_automation) يحسبهما عبر raster-service
-- (IndicatorKind.ndmi/msi — مدعومان أصلاً)، فتقرأهما الحالة القانونيّة رخيصاً ويُغذّيان
-- تأكيد الإجهاد الطيفيّ (fuse_water_stress) لتصعيد D2b (خلف feature flag، default off).
--
-- NDMI = (NIR − SWIR1)/(NIR + SWIR1) — رطوبة المحتوى. MSI = SWIR1/NIR — إجهاد مائيّ
-- (إشارة معاكسة). كلاهما من Sentinel-2 (B8/B11)، مزوّدون مجّانيّون بلا API key.
--
-- صدق: NULL = لا قيمة محسوبة بعد (الحالة تُعلن spectral_confirmation_available=false،
-- ولا تصعيد). idempotent: ADD COLUMN IF NOT EXISTS — آمن إعادة التطبيق كلّ إقلاع.

ALTER TABLE imagery_automation_fields
    ADD COLUMN IF NOT EXISTS last_ndmi_mean DOUBLE PRECISION;
ALTER TABLE imagery_automation_fields
    ADD COLUMN IF NOT EXISTS last_ndmi_date DATE;
ALTER TABLE imagery_automation_fields
    ADD COLUMN IF NOT EXISTS last_msi_mean DOUBLE PRECISION;
ALTER TABLE imagery_automation_fields
    ADD COLUMN IF NOT EXISTS last_msi_date DATE;

COMMENT ON COLUMN imagery_automation_fields.last_ndmi_mean IS 'آخر متوسّط NDMI محسوب (رطوبة المحتوى) — NULL إن لم يُحسب بعد.';
COMMENT ON COLUMN imagery_automation_fields.last_ndmi_date IS 'تاريخ صورة آخر NDMI.';
COMMENT ON COLUMN imagery_automation_fields.last_msi_mean IS 'آخر متوسّط MSI محسوب (إجهاد مائيّ) — NULL إن لم يُحسب بعد.';
COMMENT ON COLUMN imagery_automation_fields.last_msi_date IS 'تاريخ صورة آخر MSI.';
