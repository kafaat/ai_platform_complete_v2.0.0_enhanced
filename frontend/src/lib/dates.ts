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
