// UI-W6: بعد فشل إعادة جلبٍ يحتفظ React Query بآخر بيانات ناجحة مع isError=true، فكانت
// اللوحات تعرض الخطأ **وبجانبه** أرقاماً قديمة كأنّها حاليّة. السياسة الموحّدة لمساحة العمل:
//   • 401/403 ⇒ تُخفى البيانات المخبّأة (صلاحية مسحوبة — لا عرض لما لم يَعُد مسموحاً).
//   • أيّ فشل آخر (503/مهلة…) ⇒ تبقى مرئيّة لكن موسومةً «قديمة» بوقت آخر جلب ناجح.
export type CachedDataView = 'current' | 'stale' | 'hidden';

export function cachedDataView(query: { isError: boolean; error: unknown }): CachedDataView {
  if (!query.isError) return 'current';
  const status = (query.error as { response?: { status?: number } } | null | undefined)?.response?.status;
  return status === 401 || status === 403 ? 'hidden' : 'stale';
}
