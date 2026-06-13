-- ═══════════════════════════════════════════════════════════════════
-- v52_season_agronomy_fields.sql — حقول أغرونوميّة للموسم (سدّ نواقص نموذج
-- "تعديل الحقل/الموسم" على نمط Climate FieldView)
-- ═══════════════════════════════════════════════════════════════════
-- يضيف لجدول seasons: مرحلة النضج (maturity)، نوع الحراثة (tillage_type)،
-- الغلّة الفعليّة بعد الحصاد (actual_yield_kg_ha) — مقابل target_yield_kg_ha
-- المتوقّعة — وملاحظات حرّة (notes_ar). كلّها اختياريّة (ملء تدريجيّ). idempotent.

ALTER TABLE seasons
    ADD COLUMN IF NOT EXISTS maturity            VARCHAR(40),
    ADD COLUMN IF NOT EXISTS tillage_type        VARCHAR(40),
    ADD COLUMN IF NOT EXISTS actual_yield_kg_ha  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS notes_ar            TEXT;

COMMENT ON COLUMN seasons.maturity IS 'مرحلة نضج الصنف (early/medium/late) — اختياريّ';
COMMENT ON COLUMN seasons.tillage_type IS 'نوع الحراثة (مثل strip-till/no-till) — اختياريّ';
COMMENT ON COLUMN seasons.actual_yield_kg_ha IS 'الغلّة الفعليّة بعد الحصاد (كجم/هـ) مقابل target_yield_kg_ha المتوقّعة — اختياريّ';
COMMENT ON COLUMN seasons.notes_ar IS 'ملاحظات حرّة على الموسم — اختياريّ';
