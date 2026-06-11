-- v37: إثراء متقدّم للحقول — كيمياء التربة + المناخ الدقيق + تفاصيل الملكيّة
-- الفجوة: نموذج «إضافة حقل» يجمع الأساسيّات فقط؛ بيانات المختبر (pH/EC/NPK)
-- والتضاريس/المناخ (ارتفاع/ميل/منطقة مناخيّة/أمطار) وتفاصيل الملكيّة (المالك/
-- مدّة الإيجار/رقم السجلّ) تُملأ تدريجيّاً بعد الإنشاء عبر لوحة تفاصيل الحقل
-- (PATCH /api/v1/fields/{id}). كلّ الأعمدة nullable (ملء تدريجيّ). idempotent.
-- يعدّل fields (v9). تُقرأ عبر GET /api/v1/fields/{id} وتُحدَّث جزئيّاً عبر PATCH.

-- كيمياء التربة (نتائج مختبر)
ALTER TABLE fields ADD COLUMN IF NOT EXISTS soil_ph NUMERIC(4,2);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS soil_ec NUMERIC(6,2);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS soil_om NUMERIC(5,2);   -- المادّة العضويّة %
ALTER TABLE fields ADD COLUMN IF NOT EXISTS soil_n NUMERIC(6,2);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS soil_p NUMERIC(6,2);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS soil_k NUMERIC(6,2);

-- المناخ الدقيق / التضاريس
ALTER TABLE fields ADD COLUMN IF NOT EXISTS elevation_m NUMERIC(7,1);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS slope_pct NUMERIC(5,2);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS aspect VARCHAR(20);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS climate_zone VARCHAR(40);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS annual_rainfall_mm NUMERIC(7,1);

-- تفاصيل الملكيّة
ALTER TABLE fields ADD COLUMN IF NOT EXISTS owner_name VARCHAR(100);
ALTER TABLE fields ADD COLUMN IF NOT EXISTS lease_years INTEGER;
ALTER TABLE fields ADD COLUMN IF NOT EXISTS registry_no VARCHAR(50);
