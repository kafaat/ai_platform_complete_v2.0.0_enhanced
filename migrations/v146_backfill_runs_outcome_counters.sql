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

-- توسيع قيد الحالة (إسقاط القديم ثمّ إضافة الموسَّع — أسماء القيد المولّدة تلقائيّاً
-- قد تختلف، لذا نبحث عنه ونُسقطه ديناميكيّاً ثمّ نُثبّت اسماً صريحاً).
DO $$
DECLARE
    c_name TEXT;
BEGIN
    SELECT conname INTO c_name
    FROM pg_constraint
    WHERE conrelid = 'backfill_runs'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%status%IN%planned%';
    IF c_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE backfill_runs DROP CONSTRAINT %I', c_name);
    END IF;
END $$;

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
