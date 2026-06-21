// ═══════════════════════════════════════════════════════════════
// SAHOOL — أعلام الميزات (Feature Flags) · مصدر واحد
// ───────────────────────────────────────────────────────────────
// مُستخرَج من App.tsx كي تستهلكه قشرة التطبيق (NavRail) وجدول المسارات
// دون اعتماد دائريّ على App. السلوك مطابق تماماً لما كان: إخفاء شاشة فقط
// حين تكون خلفيّتها غير جاهزة فعليّاً.
//
// weather: شاشة weather-advice **موصولة بخلفيّة حقيقيّة** — نقاط المنصّة
// /api/v1/fields/{id}/weather/irrigation-advice و/disease-risk تقرأ سياق
// الحقل من القاعدة وتجلب الطقس من Open-Meteo مباشرةً، وتُعيد 503 بصدق عند
// تعذّر المصدر. لذا **مُفعَّلة افتراضيّاً**؛ تُعطَّل صراحةً بـVITE_ENABLE_WEATHER=false.
// soil: لا شاشة مستقلّة لها (تُستهلَك ضمن تقرير الاستشارة)؛ العلم للمستهلكين فقط.
// ═══════════════════════════════════════════════════════════════
import type { PageId } from '../App';

export const FEATURE_FLAGS = {
  weather: import.meta.env.VITE_ENABLE_WEATHER !== 'false',
  soil:    import.meta.env.VITE_ENABLE_SOIL === 'true',
} as const;

// الصفحات المحجوبة خلف علم مُطفأ ⇒ تُحذف من القائمة وتُمنَع في المُصيِّر.
const FLAG_GATED_PAGES: Partial<Record<PageId, boolean>> = {
  'weather-advice': FEATURE_FLAGS.weather,
};

/** هل الصفحة مُفعّلة؟ (الصفحات غير المحجوبة دائماً مُفعّلة). */
export function isPageEnabled(id: PageId): boolean {
  return FLAG_GATED_PAGES[id] !== false;
}
