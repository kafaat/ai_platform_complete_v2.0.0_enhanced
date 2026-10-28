// هل لـ(مؤشّر، تاريخ) COG محفوظ؟ — قاعدة واحدة لاختيار مصدر البلاطات في كلّ لوحة.
// ───────────────────────────────────────────────────────────────
// إصلاح «الطبقة الورديّة»: حين يكون للتاريخ COG محفوظ للمؤشّر نقرأ الطبقة المحفوظة من
// raster_assets عبر /tiles بدل تصيير CDSE الحيّ /cdse-tiles. نشترط إدراج المؤشّر صراحةً
// في indices (لا ارتداد «indices فارغة ⇒ نعم»): عند الشكّ نبقى على المسار الحيّ الذي
// يُصيّر دائماً. TrueColor يُحفَظ كـCOG RGBA مثل المؤشرات؛ وsalinity تُحفَظ باسم NDSI.
// لا تبديل بلا مؤشّر.
//
// كانت القاعدة مُضمَّنة في MapHub للعرض المفرد فقط، فلوحتا المقارنة (CompareMap) لم
// تستقبلاها وسقطتا دائماً إلى /cdse-tiles حتّى لتاريخ له COG (P2-FE-1). الآن تُشتقّ لكلّ
// لوحة من (مؤشّرها، تاريخها) بنفس الدالّة.

export interface PersistedCogDate {
  date: string;
  has_cog?: boolean;
  indices?: string[];
}

export function persistedCogIndexName(indicatorId: string | null | undefined): string | null {
  if (!indicatorId) return null;
  return indicatorId === 'salinity' ? 'NDSI' : indicatorId.toUpperCase();
}

// date: تاريخ اللوحة؛ 'latest'/فارغ ⇒ أيّ تاريخ محفوظ للمؤشّر (الخادم يختار أحدثها).
export function dateHasPersistedCog(
  indicatorId: string | null | undefined,
  date: string | null | undefined,
  dates: readonly PersistedCogDate[],
): boolean {
  const needle = persistedCogIndexName(indicatorId);
  if (!needle) return false;
  const hasIndicatorCog = (d: PersistedCogDate) =>
    !!d.has_cog &&
    Array.isArray(d.indices) &&
    d.indices.some((i) => String(i).toUpperCase() === needle);
  return date && date !== 'latest'
    ? dates.some((d) => d.date === date && hasIndicatorCog(d))
    : dates.some(hasIndicatorCog);
}
