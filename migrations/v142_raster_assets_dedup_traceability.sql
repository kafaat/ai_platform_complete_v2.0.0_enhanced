-- migrations/v142_raster_assets_dedup_traceability.sql
--
-- v142: منع تكرار أصول الراستر التاريخيّة + تعزيز التتبّع (تدقيق صور الأقمار 2026-07-05).
--
-- المشكلة (بمراجعة الكود):
--   ١) raster_assets بلا قيد تفرّد ⇒ إعادة تشغيل backfill (سنتان/٣/٥) تُراكم صفوفاً
--      مكرّرة لنفس (مستأجِر/حقل/مؤشّر/تاريخ/مشهد/COG) — غموض في التواريخ المتاحة.
--   ٢) العمود processing_job_id موجود ويُستعلَم في layer_owner_tenant لكنّه لا يُملأ ⇒
--      يسقط بحث ملكيّة الطبقة إلى مطابقة نصّيّة هشّة على مسار COG (ILIKE).
--
-- الحلّ: فهرس فريد جزئيّ (على المفاتيح غير الفارغة فقط — الصفوف القديمة بلا مشهد/COG
-- لا تتأثّر) + فهرس على processing_job_id. idempotent + آمن لإعادة التشغيل.
-- ملاحظة: الفهرس الفريد يمكّن ON CONFLICT DO UPDATE في insert_raster_asset (v142 كود).

BEGIN;

-- تنظيف تكرارات محتملة قبل إنشاء الفهرس الفريد (يُبقي الأحدث created_at لكلّ مفتاح).
-- آمن: يحذف الأقدم فقط عند تطابق كامل للمفتاح؛ لا يمسّ الصفوف الفريدة أو الناقصة المفاتيح.
DELETE FROM raster_assets a
USING raster_assets b
WHERE a.tenant_id IS NOT NULL AND a.acquisition_date IS NOT NULL
  AND a.scene_id IS NOT NULL AND a.cog_uri IS NOT NULL
  AND a.tenant_id = b.tenant_id
  AND a.field_id = b.field_id
  AND a.index_name = b.index_name
  AND a.acquisition_date = b.acquisition_date
  AND a.scene_id = b.scene_id
  AND a.cog_uri = b.cog_uri
  AND a.id < b.id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_raster_assets_scene_product
ON raster_assets (tenant_id, field_id, index_name, acquisition_date, scene_id, cog_uri)
WHERE tenant_id IS NOT NULL
  AND acquisition_date IS NOT NULL
  AND scene_id IS NOT NULL
  AND cog_uri IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_raster_assets_processing_job
ON raster_assets (processing_job_id)
WHERE processing_job_id IS NOT NULL;

COMMIT;
