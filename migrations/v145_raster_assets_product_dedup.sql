-- migrations/v145_raster_assets_product_dedup.sql
--
-- v145: إزالة تكرار أصول الراستر على مستوى «المنتَج» لا مسار COG (تدقيق الأقمار v8-F6).
--
-- المشكلة (v8-F6):
--   الفهرس الفريد v142 يتضمّن cog_uri:
--     uq_raster_assets_scene_product (tenant, field, index, date, scene, cog_uri)
--   لكن مسار المعالجة يولّد اسم COG عشوائيّاً: f"{indicator}_{uuid4().hex[:8]}.tif".
--   ⇒ إعادة معالجة نفس (مستأجِر/حقل/مؤشّر/تاريخ/مشهد) تُنتج cog_uri مختلفاً، فلا
--   يصطدم الفهرس، ويُدرَج صفّ مكرّر. مسارات sync fallback / refresh / CDSE تُدخِل
--   منتجاً مكرّراً بمسار مختلف رغم تطابق الهويّة الحقيقيّة (المنتَج نفسه).
--
-- الحلّ: اجعل الهويّة على مستوى المنتَج (بلا cog_uri). cog_uri يصير قيمةً قابلةً
--   للتحديث لا جزءاً من المفتاح. ON CONFLICT DO UPDATE (في كود insert_raster_asset)
--   يُحدّث المؤشّر إلى أحدث COG بدل تكديس صفوف.
--
-- آمن + idempotent: يُزيل التكرارات القائمة (يُبقي الأفضل جودةً/الأحدث) قبل بناء الفهرس
--   الجديد، ويحذف الفهرس القديم فقط بعد نجاح البناء. بعد v144.

BEGIN;

-- إعادة التشغيل بعد v154 (كلّ نشرٍ يُعيد تطبيق MANIFEST كاملاً):
--   v154 وسّع هويّة المنتَج لتشمل algorithm_version/qa_mask_version/field_geometry_hash
--   (product_identity_key) وأسقط uq_raster_assets_product. فإن أُعيد تشغيل الحذف أدناه
--   بعدها، لحذف إعادة معالجةٍ مشروعة (algo.v1 ثمّ algo.v2 للمشهد نفسه) لأنّ مفتاحه
--   الأضيق يراهما صفّاً مكرّراً، ثمّ أعاد بناء الفهرس الأضيق الذي يمنع إدراجها لاحقاً.
--   لذا يعمل الحذف وبناء الفهرس فقط ما دامت هويّة v154 غير موجودة (سلسلة جديدة/ما قبل v154).
DO $v145$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'raster_assets'
          AND column_name = 'product_identity_key'
    ) THEN
        RAISE NOTICE 'v145: product identity (v154) present; dedup on the narrower key skipped';
        RETURN;
    END IF;

    -- ١) إزالة التكرارات القائمة على مستوى المنتَج قبل الفهرس الفريد الأضيق.
    --    نُبقي صفّاً واحداً لكلّ (مستأجِر/حقل/مؤشّر/تاريخ/مشهد): الأعلى جودةً، ثمّ الأقلّ
    --    غيماً، ثمّ الأحدث. الصفوف الناقصة المفاتيح (بلا مشهد/تاريخ/مستأجِر) لا تتأثّر.
    DELETE FROM raster_assets
    WHERE id IN (
        SELECT id FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY tenant_id, field_id, index_name, acquisition_date, scene_id
                ORDER BY quality_score DESC NULLS LAST,
                         cloud_pct ASC NULLS LAST,
                         created_at DESC NULLS LAST,
                         id DESC
            ) AS rn
            FROM raster_assets
            WHERE tenant_id IS NOT NULL
              AND acquisition_date IS NOT NULL
              AND scene_id IS NOT NULL
        ) ranked
        WHERE ranked.rn > 1
    );

    -- ٢) الفهرس الفريد الجديد على مستوى المنتَج (بلا cog_uri).
    CREATE UNIQUE INDEX IF NOT EXISTS uq_raster_assets_product
    ON raster_assets (tenant_id, field_id, index_name, acquisition_date, scene_id)
    WHERE tenant_id IS NOT NULL
      AND acquisition_date IS NOT NULL
      AND scene_id IS NOT NULL;
END
$v145$;

-- ٣) إسقاط الفهرس القديم المتضمّن cog_uri (لم يعد يحمي من التكرار بمسار عشوائيّ).
--    بعد نجاح بناء الفهرس الجديد كي لا تبقى الجداول بلا حماية لحظةً.
DROP INDEX IF EXISTS uq_raster_assets_scene_product;

COMMIT;
