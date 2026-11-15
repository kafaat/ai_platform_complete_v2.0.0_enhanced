// dates.ts — تنسيق التواريخ الموحّد (يتسامح مع القيم الغائبة/غير الصالحة).
// كان fmtDate يُعاد كتابته في عدّة شاشات بصياغات/لغات متباينة؛ وُحِّد هنا.

// تاريخ عربيّ مختصر افتراضيّاً (يوم + شهر). القيمة الغائبة/غير الصالحة → «—».
// opts اختياريّ لتجاوز التنسيق (مثلاً إضافة weekday).
export function fmtDateAr(d?: string | null, opts?: Intl.DateTimeFormatOptions): string {
  if (!d) return '—';
  const t = new Date(d);
  return Number.isNaN(t.getTime())
    ? '—'
    : t.toLocaleDateString('ar-SA', opts ?? { day: 'numeric', month: 'long' });
}

// Raster metadata accepts date-only values and ISO acquisition times; a missing offset means UTC.
export function acquisitionUtcDay(value?: string | null): string | undefined {
  if (typeof value !== 'string') return;
  const match = /^(\d{4}-\d{2}-\d{2})(?:[T ]((?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?)(Z|[+-]\d{2}:?\d{2})?)?$/.exec(value.trim());
  if (!match) return;
  const [, day, time, offset] = match;
  const calendarDay = new Date(day + 'T00:00:00Z');
  if (!Number.isFinite(calendarDay.getTime()) || calendarDay.toISOString().slice(0, 10) !== day) return;
  if (!time) return day;
  const instant = new Date(day + 'T' + time + (offset || 'Z'));
  return Number.isFinite(instant.getTime()) ? instant.toISOString().slice(0, 10) : undefined;
}
