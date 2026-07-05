-- migrations/v146_backfill_runs_outcome_counters.sql
--
-- v146: صدق حالة تشغيلة backfill + عدّادات نتائج دقيقة (تدقيق الأقمار v8-F8 / v9-F5).
--
-- المشكلة (v8-F8 · v9-F5):
--   نهاية _process_run تضع status='completed' دائماً بعد المرور على العناصر، حتّى لو
--   فشلت كلّها. وjobs_scheduled يزيد بعد كلّ محاولة معالجة لا بعد الحفظ الفعليّ ⇒
--   «completed» تعني «انتهت الحلقة» لا «نجحت العناصر». لا عدّادات persisted/failed/skipped.
--
-- الحلّ:
--   • وسّع قيد status ليشمل 'completed_with_errors' (بعض العناصر فشل، لا الكلّ نجح).
--   • عدّادات صريحة: items_persisted / items_failed / items_skipped تُحسَب من الحفظ
--     الفعليّ (raster_assets) لا من عدد المحاولات.
--   idempotent + آمن لإعادة التشغيل. بعد v145.

BEGIN;

-- توسيع قيد الحالة ليشمل 'completed_with_errors'. القيد المضمَّن في v144
-- (``status ... CHECK (status IN (...))``) يُسمّيه Postgres اصطلاحيّاً
-- ``backfill_runs_status_check`` (نمط <table>_<column>_check)، ويُطبّعه إلى
-- ``= ANY (ARRAY[...])`` داخليّاً. نُسقطه بالاسم الاصطلاحيّ (IF EXISTS — idempotent)
-- ثمّ نُعيد إضافته موسَّعاً بنفس الاسم. (بحث ديناميكيّ عبر ILIKE '%IN%' يفشل لأنّ
-- التعريف المُطبَّع لا يحوي 'IN' — لذا الاسم الاصطلاحيّ أوثق.)
ALTER TABLE backfill_runs DROP CONSTRAINT IF EXISTS backfill_runs_status_check;
ALTER TABLE backfill_runs
    ADD CONSTRAINT backfill_runs_status_check
    CHECK (status IN (
        'planned', 'searching', 'queued', 'processing',
        'completed', 'completed_with_errors', 'failed'
    ));

-- عدّادات نتائج دقيقة (لا نعتمد jobs_scheduled كمؤشّر نجاح).
ALTER TABLE backfill_runs ADD COLUMN IF NOT EXISTS items_persisted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE backfill_runs ADD COLUMN IF NOT EXISTS items_failed    INTEGER NOT NULL DEFAULT 0;
ALTER TABLE backfill_runs ADD COLUMN IF NOT EXISTS items_skipped   INTEGER NOT NULL DEFAULT 0;

COMMIT;
