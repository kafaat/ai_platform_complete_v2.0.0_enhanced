-- v208: HISTORICAL-SEASON-COMPOSITION-02 — ربط إسقاط seasons.sim_* بسجلّ التشغيل القانونيّ.
-- المشكلة: seasons.sim_* (أحدث إسقاط تشغيليّ) لا يحمل run_id الذي أنتجه، فيُفقَد النَسَب
-- إلى season_simulation_runs (v207) — لا يمكن الجزم أيّ تشغيل أنتج القيم الظاهرة.
-- الحلّ: عمود nullable sim_run_id يُضبَط داخل نفس معاملة التشغيل عقب إدراج صفّ السجلّ.
--
-- يُدرَج قبل v206 في MANIFEST/run_migrations كي يبقى v206 (تأكيد catalog RLS النهائيّ)
-- آخِر ملفّ مطبَّق. لا جدول جديد ولا RLS جديد (seasons مُغطّى مسبقاً) — ALTER فقط.

ALTER TABLE seasons
    ADD COLUMN IF NOT EXISTS sim_run_id UUID;

COMMENT ON COLUMN seasons.sim_run_id IS
    'HISTORICAL-SEASON-COMPOSITION-02 (v208): run_id لصفّ season_simulation_runs الذي '
    'أنتج قيم sim_* الحاليّة — نَسَب الإسقاط إلى السجلّ القانونيّ append-only. تقديريّ.';
