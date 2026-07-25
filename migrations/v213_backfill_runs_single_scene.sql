-- migrations/v213_backfill_runs_single_scene.sql
--
-- v213: تمييز تشغيلة «مشهد مفرد» عن تشغيلة الـbackfill التاريخيّ (برنامج V8-05، PR1-a).
--
-- المشكلة/الفجوة:
--   • «عالِج هذا التاريخ» (منتقي التاريخ) يحتاج مساراً لاتزامنيّاً يعالج **مشهداً واحداً
--     معروفاً** لتاريخٍ اختاره المستخدم — بلا مسح STAC شهريّ (اكتشاف) ولا آلة حالة ثانية.
--   • البنية القائمة (backfill_runs/backfill_run_items، v144) هي بالفعل النموذج الدائم
--     اللاتزامنيّ الصحيح (planned→…→completed + مفتاح idempotency + RLS). إعادة استعمالها
--     تتجنّب جدول processing_jobs جديداً وحالةً موازية.
--
-- الحلّ (إضافيّ صرف، بلا جدول جديد):
--   • عمود ``run_kind`` يميّز 'backfill' (الافتراض، السلوك القائم دون تغيير) عن
--     'single_scene'. العامل يتفرّع على القيمة: 'single_scene' يتخطّى مسح الاكتشاف
--     الشهريّ ويحلّ المشهد المعروف لتاريخٍ واحد فقط.
--   • لا عمود scene_id على التشغيلة: المشهد المستهدَف يُخزَّن على ``backfill_run_items.scene_id``
--     (العنصر الوحيد المُنشأ مسبقاً)، فلا سقالة عمود غير مستهلَك.
--
-- idempotent (ADD COLUMN IF NOT EXISTS + DROP/ADD CHECK بنمط v205). ALTER فقط على جدول
-- v144 القائم — لا جدول/سياسة RLS جديدة. يُدرَج قبل v206 كي يبقى v206 آخِر مدخل.

BEGIN;

ALTER TABLE backfill_runs
    ADD COLUMN IF NOT EXISTS run_kind TEXT NOT NULL DEFAULT 'backfill';

-- قيد CHECK idempotent (نمط v205: DROP IF EXISTS ثمّ ADD كي تُعاد الهجرة بأمان تحت
-- ON_ERROR_STOP في مُشغّل compose الذي يعيد تطبيق كلّ الهجرات كلّ إقلاع).
ALTER TABLE backfill_runs DROP CONSTRAINT IF EXISTS chk_backfill_runs_run_kind;
ALTER TABLE backfill_runs
    ADD CONSTRAINT chk_backfill_runs_run_kind
        CHECK (run_kind IN ('backfill', 'single_scene'));

COMMIT;
