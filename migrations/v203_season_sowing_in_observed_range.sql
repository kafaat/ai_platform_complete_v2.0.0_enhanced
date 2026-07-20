-- v203: SEASON-RECORD-01 قيد النزاهة 2 (المواصفة §قيود-النزاهة-2) — DB-level لا تطبيقيّ فقط.
--
-- تدقيق المطابقة (المالك، 2026-07-20) كشف أنّ القيد «sowing_date ضمن نطاق المشاهدة
-- [observed_at_from, observed_at_to]» كان مفروضاً في الواجهة فقط (SeasonRecordEntryPage)،
-- بينما نصّت المواصفة صراحةً «DB-level، لا تطبيقيّة فقط». فمستدعٍ مباشر للـAPI (يتجاوز الواجهة)
-- كان يُدخِل بذاراً خارج النطاق. هذه الهجرة تُغلق الفجوة على مستوى القاعدة.
--
-- **trigger لا CHECK:** القيد يعبر جدولين (season_crop.sowing_date ↔ season_records.observed_at_*)
-- فلا يصلح CHECK بسيط — نفس نمط v201 season_harvest_after_sowing (harvest>sowing عبر جدولين).
-- **forward-only:** v201 مُطبَّقة إنتاجاً لا تُحرَّر. **idempotent:** CREATE OR REPLACE + DROP/CREATE trigger.
-- الرفض RAISE EXCEPTION ⇒ asyncpg RaiseError ⇒ 400 عبر _db_or_input_error (نفس درب harvest>sowing).

CREATE OR REPLACE FUNCTION season_crop_sowing_in_observed_range() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_from DATE;
  v_to   DATE;
BEGIN
  SELECT observed_at_from, observed_at_to INTO v_from, v_to
    FROM season_records WHERE id = NEW.season_id;
  IF v_from IS NOT NULL AND (NEW.sowing_date < v_from OR NEW.sowing_date > v_to) THEN
    RAISE EXCEPTION
      'season_crop: sowing_date (%) must be within the observed range [%, %]',
      NEW.sowing_date, v_from, v_to;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_season_crop_sowing_in_range ON season_crop;
CREATE TRIGGER trg_season_crop_sowing_in_range
  BEFORE INSERT OR UPDATE ON season_crop
  FOR EACH ROW EXECUTE FUNCTION season_crop_sowing_in_observed_range();

COMMENT ON FUNCTION season_crop_sowing_in_observed_range() IS
  'SEASON-RECORD-01 قيد النزاهة 2 (DB-level): sowing_date ضمن [observed_at_from, observed_at_to]. '
  'يُغلق فجوة تدقيق المطابقة (كان تطبيقيّاً فقط في v201). RAISE ⇒ 400.';
