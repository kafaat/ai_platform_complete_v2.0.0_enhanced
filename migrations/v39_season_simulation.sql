-- ════════════════════════════════════════════════════════════
-- SAHOOL v39 — محاكاة الموسم (Crop-model season simulation)
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة: الموسم (v32) يُخزَّن لكنّه «بيانات ساكنة» — لا تقدير إنتاج
-- ولا تتبّع نموّ. هذه الأعمدة تحفظ ناتج محاكاة محصوليّة حقيقيّة (RUE/FAO-56:
-- كفاءة استخدام الإشعاع للكتلة الحيويّة + تراكم GDD + مؤشّر LAI + احتياج الماء)
-- تُشغَّل عبر POST /api/v1/seasons/{season_id}/simulate وتُكتب على صفّ الموسم.
-- كلّ الأعمدة nullable (تُملأ عند أوّل تشغيل للمحاكاة). يعدّل seasons (v32).
-- idempotent (ADD COLUMN IF NOT EXISTS).
--
-- ⚠ صدق علمي: هذه تقديرات نموذجيّة (نطاق/مدى)، لا قياسات ميدانيّة. المعاملات
-- (RUE, HI, t_base, GDD المستهدف) إرشاديّة وتحتاج معايرة يمنيّة محلّيّة.

ALTER TABLE seasons ADD COLUMN IF NOT EXISTS sim_yield_kg_ha   NUMERIC(10, 1);  -- الإنتاج المُقدَّر (kg/ha)
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS sim_biomass_kg_ha NUMERIC(10, 1);  -- الكتلة الحيويّة فوق الأرض (kg/ha)
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS sim_gdd_total     NUMERIC(8, 1);   -- تراكم درجات النموّ الحراريّة (°C·day)
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS sim_lai_max       NUMERIC(5, 2);   -- أقصى مؤشّر مساحة ورقيّة (m²/m²)
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS sim_water_mm      NUMERIC(8, 1);   -- احتياج الماء الموسمي ETc (mm)
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS sim_ran_at        TIMESTAMPTZ;     -- وقت آخر تشغيل للمحاكاة

COMMENT ON COLUMN seasons.sim_yield_kg_ha   IS 'الإنتاج المُقدَّر (kg/ha) من محاكاة RUE/FAO-56 — تقديريّ. v39.';
COMMENT ON COLUMN seasons.sim_biomass_kg_ha IS 'الكتلة الحيويّة فوق الأرض المُقدَّرة (kg/ha). v39.';
COMMENT ON COLUMN seasons.sim_gdd_total     IS 'تراكم GDD الموسمي (°C·day). v39.';
COMMENT ON COLUMN seasons.sim_lai_max       IS 'أقصى مؤشّر مساحة ورقيّة LAI (m²/m²). v39.';
COMMENT ON COLUMN seasons.sim_water_mm      IS 'احتياج الماء الموسمي ETc المُقدَّر (mm). v39.';
COMMENT ON COLUMN seasons.sim_ran_at        IS 'وقت آخر تشغيل لمحاكاة الموسم (TIMESTAMPTZ). v39.';
