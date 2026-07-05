// ══════════════════════════════════════════════════════════════════
// realData — مصدر واحد لقاعدة «لا تستخدم بيانات تجريبيّة كأنّها حقيقيّة».
// ───────────────────────────────────────────────────────────────────
// الخلفيّة تُعلن كلّ صفٍّ ديمو صراحةً بـ`real_data: false` (انظر MOCK_FIELDS /
// fields_summary في services/api.ts). أيّ شاشة قراريّة (توصيات · اقتصاد · ترتيب
// الحقول · حقول المشكلات · المايسترو) يجب أن تستبعد هذه الصفوف من الحساب، وأن
// تُظهر شارة «عرض تجريبيّ» حين تكون البيانات المعروضة ديمو. الصفّ بلا العلم =
// حقيقيّ (لا نفترض السوء) — فقط `real_data === false` صراحةً يُعَدّ تجريبيّاً.
// ══════════════════════════════════════════════════════════════════

export interface MaybeDemo {
  real_data?: boolean;
}

/** صادق: الصفّ حقيقيّ ما لم يُعلَن صراحةً `real_data: false`. */
export function isRealData(item: MaybeDemo | null | undefined): boolean {
  return !!item && item.real_data !== false;
}

/** يُبقي الصفوف الحقيقيّة فقط — استخدمها قبل أيّ حساب قراريّ (ترتيب/توصية/اقتصاد). */
export function filterRealData<T extends MaybeDemo>(items: readonly T[] | null | undefined): T[] {
  return (items ?? []).filter((it) => isRealData(it));
}

/** هل تحوي القائمة أيّ صفٍّ تجريبيّ؟ (لعرض شارة «عرض تجريبيّ»). */
export function hasDemoData(items: readonly MaybeDemo[] | null | undefined): boolean {
  return (items ?? []).some((it) => it?.real_data === false);
}
