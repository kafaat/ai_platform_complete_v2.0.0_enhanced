-- ════════════════════════════════════════════════════════════
-- farm_id backfill — سكربت نشر يدويّ (DEPLOY-TIME) — **ليس في MANIFEST**
-- ════════════════════════════════════════════════════════════
-- الغرض: تمهيد جعل fields.farm_id إلزاميّاً (نافذة انتقاليّة). يُسند كلّ حقل بلا
-- مزرعة إلى «مزرعة افتراضيّة» لمستأجِره، ثمّ (بعد التحقّق) يضيف قيد الإلزام.
--
-- ⚠ لماذا ليس هجرة تلقائيّة (MANIFEST)؟
--   • يكتب عبر المستأجرين (farms/fields) — RLS FORCE يمنع ذلك إلّا لمالك/superuser.
--     شغّله **كمالك القاعدة/superuser** (يتجاوز RLS)، أو ضمن نافذة صيانة.
--   • القيد الإلزاميّ تغيير سلوكي (يرفض حقلاً بلا مزرعة) — يُطبَّق **بعد** التحقّق
--     من نجاح backfill + نشر تغيير الواجهة (إلزام إنشاء مزرعة أوّلاً).
-- idempotent: إعادة التشغيل آمنة (ON CONFLICT / WHERE farm_id IS NULL).
--
-- التحقّق قبل القيد:  SELECT count(*) FROM fields WHERE farm_id IS NULL;  -- توقّع 0

BEGIN;

-- (1) مزرعة افتراضيّة لكلّ مستأجِر لديه حقول بلا مزرعة (المعرّف ≤ 50 محرفاً).
INSERT INTO farms (farm_id, tenant_id, name, location)
SELECT DISTINCT
    'farm_default_' || f.tenant_id::text AS farm_id,   -- 13 + 36 = 49 ≤ VARCHAR(50)
    f.tenant_id,
    'المزرعة الافتراضيّة',
    NULL
FROM fields f
WHERE f.farm_id IS NULL
ON CONFLICT (farm_id) DO NOTHING;

-- (2) إسناد الحقول بلا مزرعة إلى مزرعة مستأجِرها الافتراضيّة.
UPDATE fields f
SET farm_id = 'farm_default_' || f.tenant_id::text
WHERE f.farm_id IS NULL;

COMMIT;

-- ── (3) قيد الإلزام — شغّله **فقط بعد** التحقّق أعلاه (count = 0) ونشر الواجهة ──
-- يُطبَّق على الجديد فوراً (NOT VALID)، ثمّ يُتحقَّق من القديم:
--   ALTER TABLE fields
--       ADD CONSTRAINT chk_fields_farm_required CHECK (farm_id IS NOT NULL) NOT VALID;
--   ALTER TABLE fields VALIDATE CONSTRAINT chk_fields_farm_required;
