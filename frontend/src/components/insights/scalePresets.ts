// ═══════════════════════════════════════════════════════════════
// SAHOOL — insights/scalePresets
// تعريفات سلالم جاهزة (نطاقات/تدرّجات) للمؤشّرات والطقس والريّ — مصدر واحد متّسق
// الألوان مع المكوّنات القائمة (NDVIGauge، weatherLayerDefinitions). تُستهلَك عبر
// GradientScale/SegmentedScale في اللوحة وشاشتَي الطقس/الريّ والمؤشّرات المكانيّة.
// ═══════════════════════════════════════════════════════════════
import type { ScaleBand } from './ScaleLegend';

// ── NDVI: نطاقات صحّة الغطاء (نفس ألوان/حدود NDVIGauge) ─────────────
export const NDVI_BANDS: ScaleBand[] = [
  { label: 'حرج', color: '#dc2626', from: -1, to: 0.1, hint: 'غطاء نباتيّ ضعيف جدّاً أو تربة عارية — افحص الإنبات/الإجهاد.' },
  { label: 'ضعيف', color: '#f97316', from: 0.1, to: 0.3, hint: 'نموّ ضعيف — قد يحتاج ريّاً/تسميداً أو فحص آفات.' },
  { label: 'متوسّط', color: '#ca8a04', from: 0.3, to: 0.5, hint: 'غطاء متوسّط — راقِب الاتّجاه عبر الزمن.' },
  { label: 'جيّد', color: '#65a30d', from: 0.5, to: 0.7, hint: 'نموّ جيّد ومنتظم.' },
  { label: 'ممتاز', color: '#16a34a', from: 0.7, to: 1.01, hint: 'كثافة خضريّة عالية وصحّة ممتازة.' },
];

// تدرّج NDVI المتّصل (RdYlGn) — يطابق أسطورة FieldIndicatorMap.
export const NDVI_GRADIENT = ['#a50026', '#f46d43', '#fee08b', '#d9ef8b', '#1a9850'];

// ── إلحاح الريّ (0..1): من مريح إلى عاجل ───────────────────────────
export const IRRIGATION_URGENCY_BANDS: ScaleBand[] = [
  { label: 'مريح', color: '#16a34a', from: 0, to: 0.25, hint: 'رطوبة كافية — لا حاجة لريّ قريب.' },
  { label: 'مراقبة', color: '#84cc16', from: 0.25, to: 0.5, hint: 'تابِع — قد يلزم ريّ خلال أيّام.' },
  { label: 'قريب', color: '#f59e0b', from: 0.5, to: 0.75, hint: 'خطّط لريّ قريب لتفادي الإجهاد المائيّ.' },
  { label: 'عاجل', color: '#dc2626', from: 0.75, to: 1.01, hint: 'إجهاد مائيّ مرتفع — ريّ فوريّ مُوصى به.' },
];

// ── مخاطر الأمراض (0..1): منخفض إلى مرتفع جدّاً ─────────────────────
export const DISEASE_RISK_BANDS: ScaleBand[] = [
  { label: 'منخفض', color: '#16a34a', from: 0, to: 0.25, hint: 'ظروف غير مواتية للمرض — مخاطرة دنيا.' },
  { label: 'متوسّط', color: '#eab308', from: 0.25, to: 0.5, hint: 'ظروف جزئيّة — راقِب الحقل والرطوبة.' },
  { label: 'مرتفع', color: '#f97316', from: 0.5, to: 0.75, hint: 'ظروف مواتية — فكّر في وقاية مُبكِرة.' },
  { label: 'مرتفع جدّاً', color: '#b91c1c', from: 0.75, to: 1.01, hint: 'ظروف عدوى عالية — تدخّل وقائيّ مُوصى به.' },
];

// ── ملاءمة الطقس للعمليّات الحقليّة (0..1): غير ملائم إلى مثاليّ ──────
export const OPERATION_SUITABILITY_BANDS: ScaleBand[] = [
  { label: 'غير ملائم', color: '#dc2626', from: 0, to: 0.3, hint: 'ظروف غير آمنة/فعّالة — أجِّل العمليّة.' },
  { label: 'مقبول', color: '#f59e0b', from: 0.3, to: 0.6, hint: 'ممكن بحذر — راعِ الرياح/الرطوبة.' },
  { label: 'جيّد', color: '#84cc16', from: 0.6, to: 0.85, hint: 'ظروف مناسبة لمعظم العمليّات.' },
  { label: 'مثاليّ', color: '#16a34a', from: 0.85, to: 1.01, hint: 'نافذة مثاليّة — نفّذ الآن.' },
];

// ── مرجع تشغيليّ سريع للطقس (للوحة): بنود بلون + تلميح ───────────────
export interface WeatherQuickRefItem {
  key: string;
  label: string;
  color: string;
  hint: string;
}

export const WEATHER_QUICK_REFERENCE: WeatherQuickRefItem[] = [
  { key: 'spraying', label: 'الرشّ', color: '#38bdf8', hint: 'أفضل عند رياح خفيفة (<15 كم/س) ورطوبة معتدلة ولا مطر.' },
  { key: 'irrigation', label: 'الريّ', color: '#22c55e', hint: 'راعِ ET₀ والرطوبة؛ تجنّب ذروة الحرارة لتقليل الفقد.' },
  { key: 'harvest', label: 'الحصاد', color: '#eab308', hint: 'يفضّل الجوّ الجافّ وانخفاض الرطوبة لجودة أعلى.' },
  { key: 'heat', label: 'الإجهاد الحراريّ', color: '#ef4444', hint: 'راقِب VPD والحرارة العالية — قد تحتاج ريّاً وقائيّاً.' },
];

// خريطة مساعِدة: تعريف سلّم لكلّ طبقة طقس مخاطرة/عمليّة (0..1) لإعادة الاستخدام.
export const RISK_BANDS_BY_LAYER: Record<string, ScaleBand[]> = {
  spraying_drift_risk: OPERATION_SUITABILITY_BANDS,
  soil_trafficability: OPERATION_SUITABILITY_BANDS,
  heat_stress: DISEASE_RISK_BANDS,
  disease_late_blight: DISEASE_RISK_BANDS,
  disease_downy_mildew: DISEASE_RISK_BANDS,
  disease_stripe_rust: DISEASE_RISK_BANDS,
};
