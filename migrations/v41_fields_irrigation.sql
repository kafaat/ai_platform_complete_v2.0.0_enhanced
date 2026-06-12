-- v41: حقل — نموذج الريّ/المياه التفصيليّ + ربط المدير بمستخدم (Progressive Profiling).
-- أعمدة متقدّمة اختياريّة (nullable) تُملأ تدريجيّاً عبر PATCH /api/v1/fields/{id}
-- (لا تُثقِل شاشة الإنشاء البسيطة). يعدّل fields (v30/v33/v37). idempotent.
ALTER TABLE fields ADD COLUMN IF NOT EXISTS irrigation_type          VARCHAR(20);   -- drip/pivot/flood/sprinkler/rainfed/subsurface
ALTER TABLE fields ADD COLUMN IF NOT EXISTS irrigation_efficiency_pct NUMERIC(5,2) CHECK (irrigation_efficiency_pct IS NULL OR (irrigation_efficiency_pct >= 0 AND irrigation_efficiency_pct <= 100));
ALTER TABLE fields ADD COLUMN IF NOT EXISTS flow_rate_m3h            NUMERIC(8,2)  CHECK (flow_rate_m3h IS NULL OR flow_rate_m3h >= 0);   -- تدفّق المضخّة م³/ساعة
ALTER TABLE fields ADD COLUMN IF NOT EXISTS pump_type               VARCHAR(30);   -- submersible/surface/solar/...
ALTER TABLE fields ADD COLUMN IF NOT EXISTS well_depth_m            NUMERIC(7,1)  CHECK (well_depth_m IS NULL OR well_depth_m >= 0);    -- عمق البئر (م)
ALTER TABLE fields ADD COLUMN IF NOT EXISTS water_ec                NUMERIC(6,2)  CHECK (water_ec IS NULL OR water_ec >= 0);            -- ملوحة الماء dS/m
-- ربط المدير بمستخدم حقيقيّ (اختياريّ، إضافيّ بجانب manager النصّيّ — غير كاسر).
-- مرجع منطقيّ إلى users.id (تُدار في auth-service بنفس القاعدة)؛ بلا FK صلب لتجنّب
-- اقتران ترتيب الهجرات عبر الخدمات.
ALTER TABLE fields ADD COLUMN IF NOT EXISTS manager_user_id         VARCHAR(64);
