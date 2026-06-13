-- migrations/v54_imagery_ndvi_value.sql
-- Stage D (Canonical Field State): قيمة NDVI الحقيقيّة لكلّ حقل (لا نضارتها فقط).
--
-- خطّ أتمتة الصور (imagery_automation) يجلب صور Sentinel من مزوّدين مجّانيّين بلا
-- API key (Element84 Earth Search / Planetary Computer / Digital Earth Africa) عبر
-- raster-service، ويحسب المؤشّرات. هذان العمودان يخزّنان آخر متوسّط NDVI محسوب +
-- تاريخه لكلّ حقل، فتقرأهما الحالة القانونيّة رخيصاً (بلا نداء حيّ لكلّ قراءة).
--
-- صدق: NULL = لا قيمة محسوبة بعد (الحالة تُعلن remote_sensing.available=false، لا
-- رقم مُلفَّق). idempotent: ADD COLUMN IF NOT EXISTS — آمن إعادة التطبيق كلّ إقلاع.

ALTER TABLE imagery_automation_fields
    ADD COLUMN IF NOT EXISTS last_ndvi_mean DOUBLE PRECISION;
ALTER TABLE imagery_automation_fields
    ADD COLUMN IF NOT EXISTS last_ndvi_date DATE;
