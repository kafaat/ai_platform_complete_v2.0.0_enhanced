-- v13_geospatial_core.sql
-- تقوية النواة الجيومكانيّة (أولويّة ١): حساب آلي لـarea_ha والمركز من الحدود.
--
-- الفجوة: field_boundaries.geom (POLYGON 4326) و area_ha موجودان، لكن area_ha
-- كان يُملأ يدويّاً. هذا trigger يحسبه آليّاً من الهندسة عند الإدراج/التحديث —
-- يجسّد "المساحة تُنتَج آليّاً عند تحديد الحقل".
--
-- يستخدم GEOGRAPHY cast لحساب مساحة دقيق بالأمتار المربّعة (يراعي كرويّة الأرض)
-- بدل مساحة مسطّحة خاطئة على إحداثيّات 4326.

-- ─── دالّة: حساب area_ha + lat/lon المركز من geom ──────────────
CREATE OR REPLACE FUNCTION compute_field_geometry()
RETURNS TRIGGER AS $$
BEGIN
    -- احسب فقط عند توفّر هندسة صالحة
    IF NEW.geom IS NOT NULL THEN
        -- المساحة بالهكتار: ST_Area على GEOGRAPHY يعطي م²، نقسم على 10000
        -- (GEOGRAPHY يحسب على سطح كروي = دقيق لليمن، لا مسطّح مشوّه)
        NEW.area_ha := ROUND(
            (ST_Area(NEW.geom::geography) / 10000.0)::numeric, 2
        );

        -- مركز الحقل (للعرض السريع وطلبات الطقس/الأقمار) لو لم يُحدّد
        IF NEW.lat IS NULL OR NEW.lon IS NULL THEN
            NEW.lat := ROUND(ST_Y(ST_Centroid(NEW.geom))::numeric, 6);
            NEW.lon := ROUND(ST_X(ST_Centroid(NEW.geom))::numeric, 6);
        END IF;
    END IF;

    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ─── Trigger: قبل الإدراج أو تحديث الهندسة ──────────────────────
DROP TRIGGER IF EXISTS trg_compute_field_geometry ON field_boundaries;
CREATE TRIGGER trg_compute_field_geometry
    BEFORE INSERT OR UPDATE OF geom ON field_boundaries
    FOR EACH ROW
    EXECUTE FUNCTION compute_field_geometry();

-- ─── دالّة مساعدة: التحقّق من صحّة الهندسة (للنواة الجيومكانيّة) ──
-- تُستخدم في طبقة الـAPI للتحقّق قبل القبول (geom صالحة + غير متقاطعة ذاتيّاً)
CREATE OR REPLACE FUNCTION is_valid_field_geom(g GEOMETRY)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN g IS NOT NULL
       AND ST_IsValid(g)
       AND ST_GeometryType(g) = 'ST_Polygon'
       AND ST_Area(g::geography) > 0;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ملاحظة: هذا الترحيل idempotent (CREATE OR REPLACE + DROP IF EXISTS) —
-- آمن لإعادة التطبيق. يتطلّب PostGIS (موجود في صورة postgis/postgis).
