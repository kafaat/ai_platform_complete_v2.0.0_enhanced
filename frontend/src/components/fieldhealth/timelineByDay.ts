/**
 * سجلّ خطّ زمنيّ واحد لكلّ يوم — المصغّرة ووقت الالتقاط والمنتَج من السجلّ نفسه.
 *
 * T2 (thumb-web): كان SatellitePage يربط اليوم بسجلّين مختلفين: `Map.set` لرابط المصغّرة
 * (الأخير يغلب) و`find` لـ`acquisition_datetime` (الأوّل يغلب). مع مشهدين لليوم نفسه
 * تعرض البطاقة صورة مشهد ووقت مشهد آخر. هنا يُختار سجلّ واحد ذرّيّاً:
 *   - أوّل سجلّ لليوم يحمل `thumbnail_url` (الخادم يرتّب تنازليّاً بوقت الالتقاط)؛
 *   - وإلّا أوّل سجلّ لليوم (وقته يبقى، وصورته null) — لا تُستعار صورة من سجلّ ووقت من آخر.
 */
export interface TimelineDayRecord {
  date: string;
  thumbnail_url?: string | null;
  thumbnail_index?: string | null;
  acquisition_datetime?: string | null;
}

export function timelineRecordByDay<R extends TimelineDayRecord>(items: readonly R[]): Map<string, R> {
  const byDay = new Map<string, R>();
  for (const item of items) {
    if (!item?.date) continue;
    const day = String(item.date).slice(0, 10);
    const prev = byDay.get(day);
    if (!prev || (!prev.thumbnail_url && item.thumbnail_url)) byDay.set(day, item);
  }
  return byDay;
}
