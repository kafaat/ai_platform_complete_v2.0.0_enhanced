-- migrations/v150_seasons_yield_nonnegative_check.sql
--
-- v150: قيود CHECK على أعمدة غلّة الموسم (Season Integrity Hardening — تدقيق طبقة المواسم).
--
-- المشكلة (بمراجعة الكود):
--   • نموذج Pydantic يمنع الغلّة السالبة (actual_yield_kg_ha / target_yield_kg_ha بـ ge=0)
--     لكنّ الأعمدة أُضيفت (v42/v52) **بلا قيد CHECK على مستوى القاعدة** ⇒ أيّ مسار كتابة
--     لا يمرّ عبر النموذج (نصّ SQL مباشر / إصلاح بيانات / تكامل مستقبليّ) قد يُدخِل قيمة سالبة.
--
-- الحلّ: قيدا CHECK دفاعيّان (defense-in-depth) يطابقان تحقّق النموذج — القيمة إمّا NULL
--   (اختياريّة، ملء تدريجيّ) أو ≥ 0. idempotent (يفحص pg_constraint قبل الإضافة) وآمن
--   لإعادة التشغيل. لا RLS/جدول جديد. بعد v149.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_seasons_actual_yield_nonneg'
    ) THEN
        ALTER TABLE seasons
            ADD CONSTRAINT chk_seasons_actual_yield_nonneg
            CHECK (actual_yield_kg_ha IS NULL OR actual_yield_kg_ha >= 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_seasons_target_yield_nonneg'
    ) THEN
        ALTER TABLE seasons
            ADD CONSTRAINT chk_seasons_target_yield_nonneg
            CHECK (target_yield_kg_ha IS NULL OR target_yield_kg_ha >= 0);
    END IF;
END $$;

COMMENT ON CONSTRAINT chk_seasons_actual_yield_nonneg ON seasons IS
    'الغلّة الفعليّة غير سالبة (NULL أو ≥ 0) — يطابق تحقّق Pydantic ge=0 على مستوى القاعدة';
COMMENT ON CONSTRAINT chk_seasons_target_yield_nonneg ON seasons IS
    'الغلّة المستهدفة غير سالبة (NULL أو ≥ 0) — يطابق تحقّق Pydantic ge=0 على مستوى القاعدة';

COMMIT;
