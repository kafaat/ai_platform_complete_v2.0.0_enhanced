// ═══════════════════════════════════════════════════════════════
// SAHOOL — أعلام الميزات (Feature Flags) · مصدر واحد
// ───────────────────────────────────────────────────────────────
// مُستخرَج من App.tsx كي تستهلكه قشرة التطبيق (NavRail) وجدول المسارات
// دون اعتماد دائريّ على App.
//
// ── فلسفة العرض (UX المُعتمَد: «أبقِ الكلّ + شارات النضج») ──────────
// الخلفيّة تحرس ~14 راوتراً متقدّماً خلف أعلام `FEATURE_*` (مُطفأة افتراضاً ⇒
// النقطة تُرجِع 404). كانت الواجهة تَسرُد تلك الصفحات وتربطها دون مزامنة العَلَم،
// فيُظهر نشرٌ افتراضيّ الصفحةَ ثمّ تنكسر بـ404 خام/فراغ. الحلّ المعتمَد ليس إخفاء
// القسم المتقدّم افتراضيّاً (لا نُراجِع الرؤية الحاليّة)، بل:
//   1) سجلّ أعلام واجهة يُطابق الخلفيّة 1:1 (الجدول أدناه) — افتراضه «مُفعَّل في
//      القائمة»؛ يُخفى صراحةً فقط بـVITE_ENABLE_X=false (للنشرات المُقلَّمة).
//   2) حالة «ميزة معطّلة» لطيفة بدل 404 الخام: حين يُرجِع نداء الصفحة 404 لميزة
//      مُطفأة، تُعرَض لوحة StateViews واضحة باسم العَلَم ودرجة النضج (لا انهيار).
//
// weather: شاشة weather-advice **موصولة بخلفيّة حقيقيّة** (Open-Meteo) ومُفعَّلة
// افتراضيّاً؛ تُعطَّل صراحةً بـVITE_ENABLE_WEATHER=false. soil: لا شاشة مستقلّة لها.
//
// ── جدول المزامنة (VITE_ENABLE_* ↔ backend FEATURE_*) للمسؤولين ──────
// كلّ صفحة متقدّمة تنادي راوتراً محروساً بعَلَم `FEATURE_*` (مُطفأ افتراضاً ⇒ 404).
// لإخفاء الصفحة من القائمة في نشرة لا تُفعِّل عَلَمها الخلفيّ، اضبط VITE_ENABLE_*=false
// وقتَ البناء؛ ولتفعيل الميزة فعليّاً اضبط `FEATURE_*` على الخادم (1/true/yes/on).
//
//   PageId                | VITE_ENABLE_*                   | backend FEATURE_*
//   ──────────────────────┼─────────────────────────────────┼──────────────────────────────
//   nl-gis                | VITE_ENABLE_NL_GIS              | FEATURE_NATURAL_LANGUAGE_GIS
//   decision-studio       | VITE_ENABLE_DECISION_STUDIO     | FEATURE_DECISION_STUDIO
//   decision-confidence   | VITE_ENABLE_DECISION_CONFIDENCE | FEATURE_DECISION_CONFIDENCE
//   execution-feedback    | VITE_ENABLE_EXECUTION_FEEDBACK  | FEATURE_EXECUTION_FEEDBACK
//   lineage               | VITE_ENABLE_UNIFIED_LINEAGE     | FEATURE_UNIFIED_LINEAGE
//   learning-dashboard    | VITE_ENABLE_LEARNING_DASHBOARD  | FEATURE_LEARNING_DASHBOARD
//   evidence-map          | VITE_ENABLE_EVIDENCE_MAP        | FEATURE_EVIDENCE_MAP
//   replay-map            | VITE_ENABLE_REPLAY_MAP          | FEATURE_REPLAY_MAP
//   operations-wall       | VITE_ENABLE_OPERATIONS_WALL     | FEATURE_OPERATIONS_WALL
//   irrigation-network    | VITE_ENABLE_IRRIGATION_NETWORK  | FEATURE_IRRIGATION_NETWORK
//   portfolio-command     | VITE_ENABLE_PORTFOLIO_COMMAND   | FEATURE_PORTFOLIO_COMMAND
//   device-twin           | VITE_ENABLE_DEVICE_TWIN         | FEATURE_DEVICE_TWIN
//
// أعلام خلفيّة بلا صفحة مخصّصة (لا مدخل واجهة): FEATURE_DELTA_SYNC، FEATURE_GIS_KERNEL.
// ═══════════════════════════════════════════════════════════════
import type { PageId } from '../App';

// قراءة عَلَم بيئيّ بمنطق «مُفعَّل افتراضيّاً» (يُخفى فقط بـ'false' الصريحة).
// أيّ قيمة غير 'false' (غياب/فارغ/'true'/'1'…) ⇒ مُفعَّل. يطابق سلوك weather.
function enabledByDefault(v: string | undefined): boolean {
  return v !== 'false';
}

export const FEATURE_FLAGS = {
  weather: enabledByDefault(import.meta.env.VITE_ENABLE_WEATHER),
  soil:    import.meta.env.VITE_ENABLE_SOIL === 'true',
} as const;

// ── سجلّ الميزات المتقدّمة (مرآة الخلفيّة) ───────────────────────────
// لكلّ صفحة متقدّمة محروسة بعَلَم خلفيّ: اسم عَلَم الواجهة (VITE_ENABLE_*)، واسم
// العَلَم الخلفيّ المُطابِق (FEATURE_*)، وعنوان عربيّ موجز يُعرَض في لوحة «معطّلة».
// `envEnabled` يُحسَب وقت التحميل من import.meta.env بمنطق «مُفعَّل افتراضيّاً».
export interface AdvancedFeature {
  page:        PageId;   // معرّف الصفحة في سجلّ المسارات
  viteFlag:    string;   // اسم متغيّر بيئة الواجهة (للتوثيق/الرسائل)
  backendFlag: string;   // اسم العَلَم الخلفيّ المُطابِق (يُعرَض في لوحة «معطّلة»)
  labelAr:     string;   // عنوان عربيّ موجز للميزة
  envEnabled:  boolean;  // هل عَلَم الواجهة يسمح بإظهار الصفحة؟ (افتراضاً true)
}

export const ADVANCED_FEATURES: AdvancedFeature[] = [
  { page: 'nl-gis',              viteFlag: 'VITE_ENABLE_NL_GIS',              backendFlag: 'FEATURE_NATURAL_LANGUAGE_GIS', labelAr: 'استعلام GIS باللغة الطبيعيّة', envEnabled: enabledByDefault(import.meta.env.VITE_ENABLE_NL_GIS) },
  { page: 'decision-studio',     viteFlag: 'VITE_ENABLE_DECISION_STUDIO',     backendFlag: 'FEATURE_DECISION_STUDIO',      labelAr: 'استوديو القرار',             envEnabled: enabledByDefault(import.meta.env.VITE_ENABLE_DECISION_STUDIO) },
  { page: 'decision-confidence', viteFlag: 'VITE_ENABLE_DECISION_CONFIDENCE', backendFlag: 'FEATURE_DECISION_CONFIDENCE',  labelAr: 'ثقة القرار الموحَّدة',        envEnabled: enabledByDefault(import.meta.env.VITE_ENABLE_DECISION_CONFIDENCE) },
  { page: 'execution-feedback',  viteFlag: 'VITE_ENABLE_EXECUTION_FEEDBACK',  backendFlag: 'FEATURE_EXECUTION_FEEDBACK',   labelAr: 'رصد حلقة التنفيذ',            envEnabled: enabledByDefault(import.meta.env.VITE_ENABLE_EXECUTION_FEEDBACK) },
  { page: 'lineage',             viteFlag: 'VITE_ENABLE_UNIFIED_LINEAGE',     backendFlag: 'FEATURE_UNIFIED_LINEAGE',      labelAr: 'سلسلة النَّسَب والدليل',       envEnabled: enabledByDefault(import.meta.env.VITE_ENABLE_UNIFIED_LINEAGE) },
  { page: 'learning-dashboard',  viteFlag: 'VITE_ENABLE_LEARNING_DASHBOARD',  backendFlag: 'FEATURE_LEARNING_DASHBOARD',   labelAr: 'لوحة رصد التعلّم',            envEnabled: enabledByDefault(import.meta.env.VITE_ENABLE_LEARNING_DASHBOARD) },
  { page: 'evidence-map',        viteFlag: 'VITE_ENABLE_EVIDENCE_MAP',        backendFlag: 'FEATURE_EVIDENCE_MAP',         labelAr: 'خريطة الدليل',               envEnabled: enabledByDefault(import.meta.env.VITE_ENABLE_EVIDENCE_MAP) },
  { page: 'replay-map',          viteFlag: 'VITE_ENABLE_REPLAY_MAP',          backendFlag: 'FEATURE_REPLAY_MAP',           labelAr: 'إعادة تشغيل الموسم',          envEnabled: enabledByDefault(import.meta.env.VITE_ENABLE_REPLAY_MAP) },
  { page: 'operations-wall',     viteFlag: 'VITE_ENABLE_OPERATIONS_WALL',     backendFlag: 'FEATURE_OPERATIONS_WALL',      labelAr: 'جدار مركز العمليّات',         envEnabled: enabledByDefault(import.meta.env.VITE_ENABLE_OPERATIONS_WALL) },
  { page: 'irrigation-network',  viteFlag: 'VITE_ENABLE_IRRIGATION_NETWORK',  backendFlag: 'FEATURE_IRRIGATION_NETWORK',   labelAr: 'توأم شبكة الريّ',             envEnabled: enabledByDefault(import.meta.env.VITE_ENABLE_IRRIGATION_NETWORK) },
  { page: 'portfolio-command',   viteFlag: 'VITE_ENABLE_PORTFOLIO_COMMAND',   backendFlag: 'FEATURE_PORTFOLIO_COMMAND',    labelAr: 'مركز قيادة المحفظة',          envEnabled: enabledByDefault(import.meta.env.VITE_ENABLE_PORTFOLIO_COMMAND) },
  { page: 'device-twin',         viteFlag: 'VITE_ENABLE_DEVICE_TWIN',         backendFlag: 'FEATURE_DEVICE_TWIN',          labelAr: 'توائم الأجهزة وثقة الحسّاس',   envEnabled: enabledByDefault(import.meta.env.VITE_ENABLE_DEVICE_TWIN) },
];

// خريطة سريعة page → ميزة متقدّمة (للبحث عن اسم العَلَم الخلفيّ/العنوان وقت العرض).
const ADVANCED_BY_PAGE: Partial<Record<PageId, AdvancedFeature>> =
  Object.fromEntries(ADVANCED_FEATURES.map((f) => [f.page, f]));

/** الميزة المتقدّمة المرتبطة بصفحة (أو undefined إن لم تكن صفحةً محروسةً بعَلَم). */
export function advancedFeatureForPage(id: PageId): AdvancedFeature | undefined {
  return ADVANCED_BY_PAGE[id];
}

// الصفحات المحجوبة خلف علم مُطفأ ⇒ تُحذف من القائمة وتُمنَع في المُصيِّر.
// تُبنى من عَلَم weather + أيّ ميزة متقدّمة عُطِّلت صراحةً (VITE_ENABLE_X=false).
// الافتراض دائماً «مُفعَّل» (لا نُراجِع الرؤية الحاليّة)؛ false الصريحة فقط تُخفي.
const FLAG_GATED_PAGES: Partial<Record<PageId, boolean>> = {
  'weather-advice': FEATURE_FLAGS.weather,
  ...Object.fromEntries(ADVANCED_FEATURES.map((f) => [f.page, f.envEnabled])),
};

/** هل الصفحة مُفعّلة؟ (الصفحات غير المحجوبة دائماً مُفعّلة). */
export function isPageEnabled(id: PageId): boolean {
  return FLAG_GATED_PAGES[id] !== false;
}
