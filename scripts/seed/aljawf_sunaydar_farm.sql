-- ═══════════════════════════════════════════════════════════════════
-- بذرة تشغيليّة: مزرعة الجوف المتكاملة / السنيدار (المستأجِر 001-aljawf-142ha)
-- ───────────────────────────────────────────────────────────────────
-- تُدخِل حقول/مواسم/فحوص تربة المزرعة الحقيقيّة في قاعدة المنصّة كي تظهر مباشرة
-- في الشاشات، من **بيانات مرجعيّة حقيقيّة** (لا تلفيق):
--   • farm_map.yaml (6 مناطق، 142 هكتار)
--   • yield_history.csv (Z1 قمح: 2023=2.6 · 2024=4.5 · 2025=6.17 طن/هـ، حصاد موزون)
--   • calibration/sunaydar_soil_reference.yaml (22 عيّنة: pH 8.2 · CaCO3 31% · ...)
--   • districts/al_jawf/climate.yaml (latitude_deg 16.15)
--
-- صدق:
--   • الإحداثيّات على مستوى **المديريّة** (الحزم، الجوف ~16.15N/44.78E)؛ حدود الحقل
--     (polygon) وGPS الحقليّ الدقيق **معلّقان** (7 عيّنات تنتظر تحقّق GPS ميدانيّ —
--     sunaydar_soil_reference.gps_pending_samples). لا نلفّق مضلّعاً؛ يرسمه المشغّل لاحقاً.
--   • idempotent: ON CONFLICT ⇒ يُحدِّث بلا تكرار. آمن للتشغيل المتكرّر.
--
-- التشغيل (المشغّل يمرّر UUID المستأجِر الفعليّ):
--   psql "$DATABASE_URL" -v tenant_id="'<TENANT-UUID>'" \
--        -f scripts/seed/aljawf_sunaydar_farm.sql
-- ═══════════════════════════════════════════════════════════════════

\set ON_ERROR_STOP on

BEGIN;

-- ── الحقول (6 مناطق من farm_map.yaml) ──────────────────────────────
INSERT INTO fields (field_id, name, area_ha, crop, soil_type, lat, lon, gov, tenant_id) VALUES
  ('aljawf_z1', 'محوري ١ (قمح)',   51.0, 'قمح',   'sandy_loam', 16.150000, 44.780000, 'الجوف', :tenant_id),
  ('aljawf_z2', 'محوري ٢ (قمح)',   51.0, 'قمح',   'sandy_loam', 16.150000, 44.782000, 'الجوف', :tenant_id),
  ('aljawf_z3', 'أعلاف (برسيم)',   10.0, 'برسيم', 'sandy_loam', 16.152000, 44.780000, 'الجوف', :tenant_id),
  ('aljawf_z4', 'غمر تجارب',        5.0, 'تجارب', 'sandy_loam', 16.152000, 44.782000, 'الجوف', :tenant_id),
  ('aljawf_z5', 'تقطير (قيمة عالية)',10.0,'—',    'sandy_loam', 16.148000, 44.780000, 'الجوف', :tenant_id),
  ('aljawf_z6', 'أشجار (حمضيات/عنب/رمان/بابايا)', 15.0, 'أشجار', 'sandy_loam', 16.148000, 44.782000, 'الجوف', :tenant_id)
ON CONFLICT (field_id) DO UPDATE
  SET name = EXCLUDED.name, area_ha = EXCLUDED.area_ha, crop = EXCLUDED.crop,
      soil_type = EXCLUDED.soil_type, lat = EXCLUDED.lat, lon = EXCLUDED.lon,
      gov = EXCLUDED.gov, tenant_id = EXCLUDED.tenant_id, updated_at = NOW();

-- ── المواسم (Z1 قمح — من yield_history.csv، حصاد موزون موثَّق) ───────
INSERT INTO seasons (season_id, tenant_id, field_id, crops, cultivar, irrigation_type,
                     sowing_date, season_end, status) VALUES
  ('aljawf_z1_2023', :tenant_id, 'aljawf_z1', '["wheat"]'::jsonb, 'sakha', 'pivot',
   DATE '2023-11-15', DATE '2024-04-10', 'closed'),
  ('aljawf_z1_2024', :tenant_id, 'aljawf_z1', '["wheat"]'::jsonb, 'sakha', 'pivot',
   DATE '2024-11-12', DATE '2025-04-08', 'closed'),
  ('aljawf_z1_2025', :tenant_id, 'aljawf_z1', '["wheat"]'::jsonb, 'sakha', 'pivot',
   DATE '2025-11-10', DATE '2026-04-05', 'active')
ON CONFLICT (season_id) DO UPDATE
  SET crops = EXCLUDED.crops, cultivar = EXCLUDED.cultivar,
      irrigation_type = EXCLUDED.irrigation_type, sowing_date = EXCLUDED.sowing_date,
      season_end = EXCLUDED.season_end, status = EXCLUDED.status, updated_at = NOW();

-- ── فحص تربة مرجعيّ (متوسّطات الـ22 عيّنة، sunaydar_soil_reference.yaml) ──
INSERT INTO soil_lab_tests (test_id, tenant_id, field_id, status, lab_name, sampled_on,
                            result, notes_ar) VALUES
  ('aljawf_z1_soilref', :tenant_id, 'aljawf_z1', 'approved',
   'مختبر وطني (NIP 2022 + السنيدار 2023)', DATE '2023-01-01',
   '{"ph": 8.2, "caco3_pct": 31, "organic_matter_pct": 0.94, "phosphorus_ppm": 2.7, "texture": "sandy_loam"}'::jsonb,
   'مرجع معايرة (متوسّط 22 عيّنة، شرق الحزم 486 هكتار). قيود: تثبيت فوسفور (pH>8 + CaCO3 31%)، نقص حديد/زنك، مادة عضوية <1%، ملوحة متوسّطة-عالية متباينة مكانيّاً. 7 عيّنات تنتظر تحقّق GPS ميدانيّ.')
ON CONFLICT (test_id) DO UPDATE
  SET status = EXCLUDED.status, lab_name = EXCLUDED.lab_name, sampled_on = EXCLUDED.sampled_on,
      result = EXCLUDED.result, notes_ar = EXCLUDED.notes_ar, updated_at = NOW();

COMMIT;

-- تحقّق سريع (اطبع ما بُذِر):
SELECT 'fields'  AS entity, count(*) FROM fields  WHERE field_id LIKE 'aljawf_%'
UNION ALL SELECT 'seasons', count(*) FROM seasons WHERE field_id LIKE 'aljawf_%'
UNION ALL SELECT 'soil_lab_tests', count(*) FROM soil_lab_tests WHERE field_id LIKE 'aljawf_%';
