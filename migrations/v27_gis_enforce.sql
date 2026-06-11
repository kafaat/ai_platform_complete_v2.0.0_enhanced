-- ════════════════════════════════════════════════════════════
-- SAHOOL v27 — فرض صحّة الهندسة على مستوى القاعدة (GIS enforcement)
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة (تدقيق التغطية، الطبقة ٢): الدالّة is_valid_field_geom
-- (ST_IsValid + Polygon + مساحة>0) موجودة منذ v13 لكنّها تُستخدم في طبقة الـAPI
-- فقط — لا فرض على القاعدة. أيّ إدراج مباشر (خارج الـAPI) بهندسة باطلة/متقاطعة
-- ذاتيّاً كان يمرّ. هنا trigger يرفضها عند الكتابة (BEFORE، يسبق فحص RLS).

CREATE OR REPLACE FUNCTION enforce_valid_field_geom()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.geom IS NOT NULL AND NOT is_valid_field_geom(NEW.geom) THEN
        RAISE EXCEPTION
            'هندسة غير صالحة: يجب أن تكون Polygon صالحاً (ST_IsValid) غير متقاطع ذاتيّاً ومساحته > 0'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- فرض على حدود الحقول (الجدول الأساس)
DROP TRIGGER IF EXISTS trg_enforce_valid_geom ON field_boundaries;
CREATE TRIGGER trg_enforce_valid_geom
    BEFORE INSERT OR UPDATE OF geom ON field_boundaries
    FOR EACH ROW EXECUTE FUNCTION enforce_valid_field_geom();

-- فرض على مناطق الإدارة (إن وُجد الجدول — أُنشئ في v14) — مُحرَّس بـto_regclass.
DO $$
BEGIN
    IF to_regclass('public.management_zones') IS NOT NULL THEN
        DROP TRIGGER IF EXISTS trg_enforce_valid_geom_zones ON management_zones;
        CREATE TRIGGER trg_enforce_valid_geom_zones
            BEFORE INSERT OR UPDATE OF geom ON management_zones
            FOR EACH ROW EXECUTE FUNCTION enforce_valid_field_geom();
    END IF;
END $$;

COMMENT ON FUNCTION enforce_valid_field_geom() IS
    'يرفض الهندسة غير الصالحة عند الكتابة (فرض GIS على القاعدة، لا API فقط). v27.';
