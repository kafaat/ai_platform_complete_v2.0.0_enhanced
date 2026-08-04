/**
 * وقت التقاط المشهد — يُعرَض بـUTC صراحةً، ولا يُحوَّل إلى توقيت المتصفّح.
 *
 * السبب ليس تفضيلاً: بطاقة الخطّ الزمنيّ تعرض **تاريخ** الالتقاط (`date`)، وهو مشتقّ
 * خادميّاً من طابع STAC بقصّ أوّل عشرة محارف من ISO8601 **UTC**. فلو عُرِض الوقت
 * بتوقيت المتصفّح لظهر سطران متناقضان على البطاقة نفسها: تاريخ بـUTC ووقت محلّيّ قد
 * يقع في اليوم السابق أو التالي. الوسم `UTC` يجعل القيمتين على محور واحد.
 *
 * ولا نستعمل `new Date(...).getUTCHours()` هنا: `new Date('2026-08-04')` (تاريخ بلا
 * وقت) يُفسَّر UTC بينما `new Date('2026-08-04T10:37:00')` (بلا لاحقة) يُفسَّر محلّيّاً
 * — فخّ مقيس في هذه الشجرة. القراءة من النصّ مباشرةً لا تقع فيه.
 */

const ISO_UTC =
  /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?\s*(Z|[+-]\d{2}:?\d{2})?$/;

export interface CaptureTime {
  /** `HH:MM UTC` — أو `null` إن لم يُسجَّل طابع زمنيّ (لا اختلاق ساعة). */
  label: string | null;
  /** جزء التاريخ من الطابع الزمنيّ نفسه (`YYYY-MM-DD`). */
  isoDate: string | null;
  /**
   * `true` حين يخالف تاريخُ الطابع الزمنيّ تاريخَ البطاقة.
   *
   * هذا ليس تجميلاً: البطاقة تدّعي «صورة يوم كذا»، والطابع هو الشاهد الوحيد على ذلك.
   * اختلافهما يعني أنّ التاريخ اشتُقّ من مصدر آخر (وقت معالجة، أو مشهد جار). يُعرَض
   * ولا يُبتلَع — إخفاؤه يجعل تاريخاً خاطئاً يبدو مؤكَّداً.
   */
  mismatch: boolean;
}

const EMPTY: CaptureTime = { label: null, isoDate: null, mismatch: false };

/**
 * @param acquisition الطابع الزمنيّ كما ورد من الخادم (قد يكون null/undefined).
 * @param cardDate تاريخ البطاقة `YYYY-MM-DD` للمقارنة.
 */
export function captureTime(
  acquisition: string | null | undefined,
  cardDate?: string | null,
): CaptureTime {
  if (typeof acquisition !== 'string') return EMPTY;
  const match = ISO_UTC.exec(acquisition.trim());
  if (!match) return EMPTY;

  const [, year, month, day, hour, minute, , zone] = match;
  // طابع بلا منطقة زمنيّة صريحة ليس UTC مُثبَتاً — نعرض التاريخ ولا ندّعي ساعة UTC.
  const isUtc = zone === 'Z' || zone === '+00:00' || zone === '+0000';
  const isoDate = `${year}-${month}-${day}`;
  const normalizedCard = typeof cardDate === 'string' ? cardDate.slice(0, 10) : null;

  return {
    label: isUtc ? `${hour}:${minute} UTC` : null,
    isoDate,
    mismatch: Boolean(normalizedCard && normalizedCard.length === 10 && normalizedCard !== isoDate),
  };
}

export default captureTime;
