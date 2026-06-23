-- SAHOOL v64 — migrations/v64_seasons_row_version.sql
-- توسيع التزامن التفاؤليّ (Optimistic Concurrency) إلى المواسم — يكمّل v61 (fields).
--
-- المشكلة نفسها كـv61: عاملان يعدّلان نفس الموسم دون اتّصال ثمّ يتزامنان ⇒ الكتابة
-- الأخيرة تطمس الأولى بصمت. update_season يقفل الصفّ (FOR UPDATE) فيُسلسِل الكتابات،
-- لكنّه لا يكشف أنّ العميل بنى تعديله على نسخة قديمة — يحتاج عمّاد إصدار.
--
-- لماذا trigger هنا (لا رفع تطبيقيّ كـv61): للموسم مسارات كتابة متعدّدة غير
-- update_season — محاكاة /simulate (sim_*)، والإغلاق الآليّ للموسم النشط القديم
-- في create_season. رفعٌ تطبيقيّ في update_season وحده يترك تلك المسارات لا تُحدِّث
-- row_version، فيفوت كشفُ تعارضٍ نشأ عنها. trigger BEFORE UPDATE يرفع الإصدار على
-- **كلّ** كتابة مهما كان مصدرها ⇒ أيّ تغيير يُبطِل base_version قديماً حتميّاً.
--
-- متوافق رجعيّاً: العملاء الذين لا يرسلون base_version يبقون على السلوك الحاليّ.
-- DEFAULT 1 NOT NULL يملأ الصفوف القائمة. idempotent.

BEGIN;

-- ① عمّاد الإصدار. seasons محميّ بـRLS أصلاً (v32) ⇒ العمود الجديد مشمول.
ALTER TABLE seasons ADD COLUMN IF NOT EXISTS row_version INTEGER NOT NULL DEFAULT 1;

-- ② دالّة رفع الإصدار — عامّة (قابلة لإعادة الاستخدام لجداول أخرى لاحقاً).
--    تُسند NEW.row_version = OLD.row_version + 1 على كلّ UPDATE. CREATE OR REPLACE
--    فهي idempotent.
CREATE OR REPLACE FUNCTION bump_row_version() RETURNS trigger AS $$
BEGIN
    NEW.row_version := OLD.row_version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ③ trigger الرفع على seasons — BEFORE UPDATE فيُطبَّق قبل كتابة الصفّ.
DROP TRIGGER IF EXISTS trg_seasons_row_version ON seasons;
CREATE OR REPLACE TRIGGER trg_seasons_row_version
    BEFORE UPDATE ON seasons
    FOR EACH ROW EXECUTE FUNCTION bump_row_version();

COMMENT ON COLUMN seasons.row_version IS
    'عمّاد تزامن تفاؤليّ — يرفعه trg_seasons_row_version على كلّ UPDATE (أيّ مسار '
    'كتابة). update_season يقارن base_version المُرسَل به ويردّ 409 عند التعارض. '
    'يكمّل v61 (fields). راجع v64.';

COMMIT;
