// cropPropagation — يعكس نقاط backend اليتيمة (P3) للمعرفة الزراعيّة الاختصاصيّة بلا قارئ واجهة:
//   POST /api/v1/crop-suitability            (crop_suitability.py — ترتيب ملاءمة مرجّح)
//   POST /api/v1/crop-twin/compose           (routers/crop_twin.py — تركيب حالة محصول dry-run)
//   GET  /api/v1/propagation/methods + /method-guide + /rootstock (propagation_advisor.py)
//   GET  /api/v1/practices/list + /guide      (seed_and_practices.py — أساليب محسّنة)
//   GET  /api/v1/crops/drought-resilience + /compare-drought-resilience (drought_resilience.py)
//   POST /api/v1/seed/evaluate-source         (seed_and_practices.py — تقييم مصدر بذار)
//   GET  /api/v1/sampling/strategy            (zone_sampling.py — استراتيجيّة أخذ العيّنات)
//
// صدق صارم (نفس عرف irrigationDecisionAids/agronomyConsistency): الأحكام والنصوص كلّها من
// الخادم وتمرّ حرفيّاً (rating_ar/risk_level_ar/reasons_ar/advice_ar/flags_ar/note_ar/verdict…)
// — لا يُعاد الحكم في الواجهة. null/غائب ⇒ «—» أو يسقط (لا تصفير ولا تلفيق). خرائط القيم
// المعروفة هنا للتلوين فقط؛ القيمة المجهولة ⇒ محايد #64748b + نصّ الخادم كما جاء.

const DASH = '—';
/** رماديّ محايد للقيم المجهولة — نفس محايد riskColor في approvalsConsole/agronomyConsistency. */
const NEUTRAL = '#64748b';

export interface DisplayFact {
  label: string;
  value: string;
}

/** تنسيق رقم للعرض — null/undefined/غير منتهٍ ⇒ «—» (لا تصفير). */
export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return v.toFixed(digits);
}

/** رسالة الخادم لاستجابة غير مدعومة (supported=false ⇒ message_ar) — تمرّ كما جاءت. */
export function serverMessage(
  resp: { supported?: boolean; message_ar?: string } | null | undefined,
): string | null {
  if (!resp || resp.supported !== false) return null;
  return resp.message_ar ?? null;
}

// ═══ 1. ملاءمة المحاصيل — POST /api/v1/crop-suitability ═══════════════════════

/** crop_suitability.py — SuitabilityScore.to_dict(). */
export interface SuitabilityScore {
  crop?: string;
  name_ar?: string;
  score?: number; // 0-1
  rating_ar?: string; // ممتاز/جيّد/حدّي/غير مناسب (نصّ الخادم)
  reasons_ar?: string[];
}
export interface CropSuitabilityResponse {
  ranked?: SuitabilityScore[];
  note_ar?: string;
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** تلوين تقييم الملاءمة — القيم من rank_crops (نصّ عربيّ حرفيّ)؛ المجهول ⇒ محايد. */
const SUITABILITY_RATING_COLORS: Record<string, string> = {
  'ممتاز': '#86efac',
  'جيّد': '#7dd3fc',
  'حدّي': '#fdba74',
  'غير مناسب': '#fca5a5',
};
export function suitabilityRatingColor(rating_ar: string | null | undefined): string {
  return (rating_ar && SUITABILITY_RATING_COLORS[rating_ar]) || NEUTRAL;
}

/** المحاصيل المرتّبة كما رتّبها الخادم — بلا مصفوفة ⇒ []. */
export function rankedCrops(resp: CropSuitabilityResponse | null | undefined): SuitabilityScore[] {
  if (!resp || !Array.isArray(resp.ranked)) return [];
  return resp.ranked;
}

// ═══ 2. تركيب حالة المحصول — POST /api/v1/crop-twin/compose ═══════════════════

export interface ComposeStressFlag {
  code?: string;
  label_ar?: string;
}
export interface ComposeQuality {
  confidence?: number;
  data_quality?: string; // high/medium/low
  assumptions?: string[];
  assumptions_ar?: string[];
  calibrated?: boolean;
}
/** routers/crop_twin.py — compose_crop_twin() (dry-run؛ الأحكام موسومة calibrated=false). */
export interface CropTwinComposeResponse {
  field_id?: string | null;
  crop?: string | null;
  crop_known?: boolean;
  dynamic_kc?: number;
  kc_fapar?: number | null;
  kc_source_ar?: string;
  stress_flags?: ComposeStressFlag[];
  quality?: ComposeQuality;
  calibrated?: boolean;
  warnings_ar?: string[];
  disabled?: boolean;
}

/** أعلام إجهاد حالة المحصول كما يعيدها الخادم — بلا مصفوفة ⇒ []. */
export function composeStressFlags(resp: CropTwinComposeResponse | null | undefined): ComposeStressFlag[] {
  if (!resp || !Array.isArray(resp.stress_flags)) return [];
  return resp.stress_flags;
}

/** حقائق التركيب (Kc الديناميكيّ + fAPAR) — الغائب يسقط لا يُصفَّر. */
export function composeFacts(resp: CropTwinComposeResponse | null | undefined): DisplayFact[] {
  if (!resp) return [];
  const facts: DisplayFact[] = [];
  if (resp.dynamic_kc != null) facts.push({ label: 'Kc الديناميكيّ', value: fmtNum(resp.dynamic_kc, 3) });
  if (resp.kc_fapar != null) facts.push({ label: 'Kc عبر fAPAR', value: fmtNum(resp.kc_fapar, 3) });
  return facts;
}

/** تلوين جودة المدخلات (data_quality) — high/medium/low؛ المجهول ⇒ محايد. */
const QUALITY_COLORS: Record<string, string> = {
  high: '#86efac',
  medium: '#fdba74',
  low: '#fca5a5',
};
export function qualityColor(q: string | null | undefined): string {
  return (q && QUALITY_COLORS[q]) || NEUTRAL;
}

// ═══ 3. الإكثار الخضري — GET /api/v1/propagation/* ════════════════════════════

export interface PropagationMethodSummary {
  method?: string;
  name_ar?: string;
  what_ar?: string;
  best_for_ar?: string;
}
export interface PropagationMethodsResponse {
  methods?: PropagationMethodSummary[];
  principle_ar?: string;
  caution_ar?: string;
  disabled?: boolean;
}
export interface PropagationMethodGuideResponse {
  supported?: boolean;
  method?: string;
  name_ar?: string;
  what_ar?: string;
  types_ar?: string[];
  tip_ar?: string;
  best_for_ar?: string;
  disclaimer_ar?: string;
  message_ar?: string;
  disabled?: boolean;
}
export interface RootstockStress {
  stress?: string;
  label_ar?: string;
}
export interface RootstockResponse {
  stress?: string;
  stress_ar?: string;
  advice_ar?: string;
  related_ar?: string;
  principle_ar?: string;
  all_stresses_ar?: RootstockStress[];
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** طرق الإكثار كما يرتّبها الخادم — بلا مصفوفة ⇒ []. */
export function propagationMethods(resp: PropagationMethodsResponse | null | undefined): PropagationMethodSummary[] {
  if (!resp || !Array.isArray(resp.methods)) return [];
  return resp.methods;
}

/** أنواع طريقة إكثار محدّدة — unsupported/بلا مصفوفة ⇒ [] (message_ar عبر serverMessage). */
export function methodGuideTypes(resp: PropagationMethodGuideResponse | null | undefined): string[] {
  if (!resp?.supported || !Array.isArray(resp.types_ar)) return [];
  return resp.types_ar;
}

/** كلّ الإجهادات المتاحة لاختيار الأصل — بلا مصفوفة ⇒ []. */
export function rootstockStresses(resp: RootstockResponse | null | undefined): RootstockStress[] {
  if (!resp || !Array.isArray(resp.all_stresses_ar)) return [];
  return resp.all_stresses_ar;
}

// ═══ 4. الأساليب الزراعيّة المحسّنة — GET /api/v1/practices/* ══════════════════

export interface PracticeSummary {
  practice?: string;
  name_ar?: string;
  what_ar?: string;
}
export interface PracticesListResponse {
  practices?: PracticeSummary[];
  disabled?: boolean;
}
export interface PracticeGuideResponse {
  supported?: boolean;
  practice?: string;
  name_ar?: string;
  what_ar?: string;
  benefits_ar?: string[];
  caution_ar?: string;
  yemen_note_ar?: string;
  disclaimer_ar?: string;
  message_ar?: string;
  disabled?: boolean;
}

/** الأساليب المدعومة كما يعيدها الخادم — بلا مصفوفة ⇒ []. */
export function practicesList(resp: PracticesListResponse | null | undefined): PracticeSummary[] {
  if (!resp || !Array.isArray(resp.practices)) return [];
  return resp.practices;
}

/** فوائد أسلوب محسّن — unsupported/بلا مصفوفة ⇒ [] (message_ar عبر serverMessage). */
export function practiceBenefits(resp: PracticeGuideResponse | null | undefined): string[] {
  if (!resp?.supported || !Array.isArray(resp.benefits_ar)) return [];
  return resp.benefits_ar;
}

// ═══ 5. صمود الجفاف — GET /api/v1/crops/(compare-)drought-resilience ══════════

export interface DroughtComponents {
  root_depth_m?: number | null;
  root_score?: number | null;
  threshold_ece?: number | null;
  salt_score?: number | null;
  flowering_safe_max_c?: number | null;
  heat_headroom_c?: number | null;
}
/** drought_resilience.py — compute_drought_resilience(). بلا صفات ⇒ resilience_score=null + note_ar. */
export interface DroughtResilienceResponse {
  crop_id?: string;
  resilience_score?: number | null;
  risk_level_ar?: string; // نصّ الخادم الحرفيّ
  components?: DroughtComponents;
  confidence?: string; // none/low/moderate
  source_note_ar?: string;
  note_ar?: string;
  heat_warning_ar?: string;
  heat_basis_ar?: string;
  heat_irrigation_caveat_ar?: string;
  disabled?: boolean;
}
export interface CompareDroughtResilienceResponse {
  ranked_by_resilience?: DroughtResilienceResponse[];
  most_resilient?: string | null;
  note_ar?: string;
  honesty_note_ar?: string;
  disabled?: boolean;
}

/** تلوين مستوى تحمّل الجفاف — القيم من risk() الحرفيّة؛ المجهول ⇒ محايد. */
const DROUGHT_RISK_COLORS: Record<string, string> = {
  'تحمّل عالٍ': '#86efac',
  'تحمّل متوسّط': '#7dd3fc',
  'تحمّل محدود': '#fdba74',
  'حسّاس للجفاف': '#fca5a5',
};
export function droughtRiskColor(risk_level_ar: string | null | undefined): string {
  return (risk_level_ar && DROUGHT_RISK_COLORS[risk_level_ar]) || NEUTRAL;
}

/** مكوّنات درجة الصمود (كلّ من صفة موثّقة) — الغائب/null يسقط لا يُصفَّر. */
export function droughtComponentFacts(resp: DroughtResilienceResponse | null | undefined): DisplayFact[] {
  const c = resp?.components;
  if (!c) return [];
  const facts: DisplayFact[] = [];
  if (c.root_depth_m != null) facts.push({ label: 'عمق الجذور', value: `${fmtNum(c.root_depth_m, 1)} م` });
  if (c.threshold_ece != null) facts.push({ label: 'عتبة الملوحة ECe', value: fmtNum(c.threshold_ece, 1) });
  if (c.flowering_safe_max_c != null) facts.push({ label: 'حدّ حرارة الإزهار', value: `${fmtNum(c.flowering_safe_max_c, 0)}°م` });
  if (c.heat_headroom_c != null) facts.push({ label: 'هامش الحرارة', value: `${fmtNum(c.heat_headroom_c, 1)}°م` });
  return facts;
}

/** المحاصيل المرتّبة بالصمود — بلا مصفوفة ⇒ []. */
export function comparedCrops(resp: CompareDroughtResilienceResponse | null | undefined): DroughtResilienceResponse[] {
  if (!resp || !Array.isArray(resp.ranked_by_resilience)) return [];
  return resp.ranked_by_resilience;
}

// ═══ 6. تقييم مصدر البذار — POST /api/v1/seed/evaluate-source ═════════════════

/** seed_and_practices.py — evaluate_seed_source(). */
export interface SeedEvaluateResponse {
  acceptable?: boolean;
  summary_ar?: string;
  flags_ar?: string[];
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** تلوين حكم القبول — منطقيّ من الخادم (لا إعادة حكم). null ⇒ محايد. */
export function seedAcceptableColor(acceptable: boolean | null | undefined): string {
  if (acceptable === true) return '#86efac';
  if (acceptable === false) return '#fca5a5';
  return NEUTRAL;
}

/** أعلام تقييم البذار كما يعيدها الخادم (✓/⚠ تمرّ حرفيّاً) — بلا مصفوفة ⇒ []. */
export function seedFlags(resp: SeedEvaluateResponse | null | undefined): string[] {
  if (!resp || !Array.isArray(resp.flags_ar)) return [];
  return resp.flags_ar;
}

// ═══ 7. استراتيجيّة أخذ العيّنات — GET /api/v1/sampling/strategy ═══════════════

export interface SamplingDepthAdvice {
  depths_cm?: string[];
  note_ar?: string;
  is_estimate?: boolean;
}
/** zone_sampling.py — recommend_sampling_strategy() + depth_advice المدمج. */
export interface SamplingStrategyResponse {
  method?: string; // zone/grid/grid_coarse
  rationale_ar?: string;
  recommended_zones?: number | null;
  recommended_samples?: number | null;
  cores_per_composite?: number | null;
  note_ar?: string;
  is_estimate?: boolean;
  calibration_advice_ar?: string;
  depth_advice?: SamplingDepthAdvice;
  disabled?: boolean;
}

/** تلوين وتسمية نوع الاستراتيجيّة — القيم من recommend_sampling_strategy؛ المجهول ⇒ محايد بمفتاحه. */
const SAMPLING_METHOD_LABELS: Record<string, { label_ar: string; color: string }> = {
  zone: { label_ar: 'مناطق إدارة (zone)', color: '#86efac' },
  grid: { label_ar: 'شبكة (grid)', color: '#fdba74' },
  grid_coarse: { label_ar: 'شبكة خشنة', color: '#7dd3fc' },
};
export function samplingMethodBadge(method: string | null | undefined): { label_ar: string; color: string } {
  if (method && SAMPLING_METHOD_LABELS[method]) return SAMPLING_METHOD_LABELS[method];
  return { label_ar: method ?? DASH, color: NEUTRAL };
}

/** حقائق الاستراتيجيّة (مناطق/عيّنات/cores) — الغائب/null يسقط لا يُصفَّر. */
export function samplingFacts(resp: SamplingStrategyResponse | null | undefined): DisplayFact[] {
  if (!resp) return [];
  const facts: DisplayFact[] = [];
  if (resp.recommended_zones != null) facts.push({ label: 'المناطق', value: fmtNum(resp.recommended_zones) });
  if (resp.recommended_samples != null) facts.push({ label: 'العيّنات المخبريّة', value: fmtNum(resp.recommended_samples) });
  if (resp.cores_per_composite != null) facts.push({ label: 'cores لكلّ عيّنة', value: fmtNum(resp.cores_per_composite) });
  return facts;
}

/** أعماق أخذ العيّنة كما يعيدها الخادم — بلا مصفوفة ⇒ []. */
export function samplingDepths(resp: SamplingStrategyResponse | null | undefined): string[] {
  const d = resp?.depth_advice?.depths_cm;
  return Array.isArray(d) ? d : [];
}
