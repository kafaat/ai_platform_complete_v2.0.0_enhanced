-- SAHOOL v59 — migrations/v59_boundary_topology_fn.sql
-- #15 — محرّك الطوبولوجيا للحدود (Polygon/Topology Engine).
--
-- الهدف: دالّة PostGIS حتميّة (deterministic) تنظّف طوبولوجيا مضلّع الحدّ —
-- وهي بالضبط مرحلة «التبسيط / إصلاح الطوبولوجيا / إزالة الثقوب / تنعيم الحواف»
-- (Simplification / Topology Fix / Hole Removal / Edge Smoothing) في خطّ أنابيب
-- حدود الحقل (Field Boundary pipeline).
--
-- ملاحظة جوهريّة: هذه المرحلة حتميّة بالكامل ولا تتضمّن أيّ تعلّم آليّ (no ML).
-- مخرجاتها مضلّعات تشغيليّة (operational polygons) جاهزة للاستخدام في الإنتاج —
-- لا أقنعة بحثيّة (research masks). فالحتميّة هنا مقصودة: نفس المدخل ينتج نفس
-- المخرج دائماً، فلا تعتمد جودة الحدّ التشغيليّ على نموذج احتماليّ.
--
-- field_boundaries.geom من نوع GEOMETRY(POLYGON, 4326).
-- يطبّقه CI Integration Tests على PostGIS حقيقيّ (صورة postgis/postgis) عبر تمرير
-- كامل MANIFEST، فدوالّ PostGIS (ST_MakeValid / ST_SimplifyPreserveTopology /
-- ST_RemoveRepeatedPoints / ST_CollectionExtract / ST_Area) متوفّرة هناك.
-- idempotent عبر CREATE OR REPLACE — آمن إعادة التطبيق كلّ إقلاع.

-- ══════════════════════════════════════════════════════════════════
-- الدالّة: sahool_clean_boundary_geom(p_geom, p_tolerance_m)
-- ══════════════════════════════════════════════════════════════════
-- الخطوات (بالترتيب):
--   1) NULL → NULL (مدخل فارغ يعيد فارغاً).
--   2) ST_MakeValid: إصلاح التقاطعات الذاتيّة والحلقات غير الصالحة.
--   3) ST_RemoveRepeatedPoints: إسقاط الرؤوس المكرّرة المتطابقة.
--   4) إن صار الناتج GEOMETRYCOLLECTION/MULTIPOLYGON: نستخرج المضلّعات
--      (ST_CollectionExtract(...,3)) ونُبقي المضلّع الأكبر مساحةً (هو الحقل)،
--      ونُسقط الشظايا (slivers) الناتجة عن MakeValid.
--   5) ST_SimplifyPreserveTopology: تبسيط مع الحفاظ على الطوبولوجيا.
--
-- ⚠ تقريب وحدة التحمّل (tolerance) — اعتراف صادق:
--   في الإسقاط 4326 (درجات) تكون tolerance بالدرجات لا بالأمتار. نحوّل المتر إلى
--   درجة تقريبياً بقسمته على 111320.0 (≈ طول درجة خطّ عرض بالمتر). هذا تقريبٌ
--   صالحٌ قرب خطّ الاستواء وعند خطوط عرض اليمن (≈ 12°–19° شمالاً)، حيث يبقى
--   الانحراف صغيراً عند مقياس الحقل. عند خطوط عرض عالية يتقلّص طول درجة خطّ
--   الطول (cos(lat)) فيصبح التقريب أقلّ دقّة. التحسين المستقبليّ: استخدام
--   geography أو ST_Transform إلى إسقاط متريّ محليّ (مثل UTM) قبل التبسيط.

CREATE OR REPLACE FUNCTION sahool_clean_boundary_geom(
    p_geom        geometry,
    p_tolerance_m double precision DEFAULT 5.0
)
RETURNS geometry
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_valid   geometry;   -- ناتج ST_MakeValid (مرجع احتياطيّ عند الفشل)
    v_geom    geometry;   -- الهندسة قيد المعالجة
    v_tol_deg double precision;  -- وحدة التحمّل محوّلة إلى درجات (تقريب — انظر أعلاه)
BEGIN
    -- (1) مدخل فارغ → ناتج فارغ.
    IF p_geom IS NULL THEN
        RETURN NULL;
    END IF;

    -- (2) إصلاح الصلاحيّة الطوبولوجيّة (التقاطعات الذاتيّة/الحلقات المعطوبة).
    v_valid := ST_MakeValid(p_geom);
    v_geom  := v_valid;

    -- نلفّ بقيّة المعالجة في حارس استثناء: أيّ مدخل منحطّ (degenerate) يعيد
    -- ناتج ST_MakeValid بدل أن يُخفق التحديث برمّته.
    BEGIN
        -- (3) إسقاط الرؤوس المكرّرة المتطابقة.
        v_geom := ST_RemoveRepeatedPoints(v_geom);

        -- (4) إن كان الناتج مجموعة/متعدّد مضلّعات: استخرج المضلّعات وأبقِ الأكبر
        --     مساحةً (الحقل)، وأسقط الشظايا (slivers).
        IF ST_GeometryType(v_geom) IN ('ST_GeometryCollection', 'ST_MultiPolygon') THEN
            SELECT poly.geom
              INTO v_geom
              FROM (
                    SELECT (ST_Dump(ST_CollectionExtract(v_geom, 3))).geom AS geom
                   ) AS poly
             ORDER BY ST_Area(poly.geom) DESC
             LIMIT 1;

            -- إن لم يتبقَّ أيّ مضلّع (extract لم يُرجع شيئاً) نعود لناتج MakeValid.
            IF v_geom IS NULL THEN
                RETURN v_valid;
            END IF;
        END IF;

        -- (5) التبسيط مع الحفاظ على الطوبولوجيا.
        --     تحويل المتر → درجة (تقريب — انظر كتلة التعليق أعلاه).
        v_tol_deg := p_tolerance_m / 111320.0;
        v_geom := ST_SimplifyPreserveTopology(v_geom, v_tol_deg);

        -- قد يُعيد التبسيط NULL لهندسة منحطّة جدّاً — نعود حينها لناتج MakeValid.
        IF v_geom IS NULL THEN
            RETURN v_valid;
        END IF;

        RETURN v_geom;
    EXCEPTION
        WHEN OTHERS THEN
            -- مدخل منحطّ: أعِد ناتج ST_MakeValid بدل رفع الخطأ.
            RETURN v_valid;
    END;
END;
$$;

COMMENT ON FUNCTION sahool_clean_boundary_geom(geometry, double precision) IS
    'مرحلة تنظيف الطوبولوجيا الحتميّة لخطّ أنابيب حدود الحقل (#15): MakeValid + '
    'إزالة الرؤوس المكرّرة + إبقاء المضلّع الأكبر مساحةً + تبسيط حافظ للطوبولوجيا. '
    'بلا ML — مضلّعات تشغيليّة لا أقنعة بحثيّة. تقريب المتر→درجة صالح قرب خطوط عرض اليمن.';

-- ══════════════════════════════════════════════════════════════════
-- الاستخدام المقصود (لا نطبّقه هنا — لا نُغيّر البيانات في الـmigration):
-- ══════════════════════════════════════════════════════════════════
--   UPDATE field_boundaries
--      SET geom = sahool_clean_boundary_geom(geom, 5.0)
--    WHERE geom IS NOT NULL
--      AND review_status = 'unreviewed';   -- مثال: حقول لم تُراجَع بعد
--
-- (التحديث الجماعيّ متروك لمهمّة تشغيليّة صريحة؛ الـmigration يُنشئ الدالّة فقط.)
