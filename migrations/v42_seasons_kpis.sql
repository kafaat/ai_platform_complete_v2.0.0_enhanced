-- v42: موسم — مؤشّرات أداء زراعيّة (KPIs) أساس التحليلات: الإنتاج المستهدف،
-- كثافة النبات، تباعد الصفوف، مصدر البذور. كلّها nullable (ملء تدريجيّ).
-- يعدّل seasons (v32). idempotent.
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS target_yield_kg_ha   NUMERIC(10,1) CHECK (target_yield_kg_ha IS NULL OR target_yield_kg_ha >= 0);  -- الإنتاج المستهدف (kg/ha)
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS plant_density        NUMERIC(12,2) CHECK (plant_density IS NULL OR plant_density >= 0);          -- كثافة النبات (نبات/م²)
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS row_spacing_cm       NUMERIC(6,2)  CHECK (row_spacing_cm IS NULL OR row_spacing_cm >= 0);        -- تباعد الصفوف (سم)
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS seed_variety_source  VARCHAR(100);  -- مصدر/منشأ البذور (شركة/جهة)
