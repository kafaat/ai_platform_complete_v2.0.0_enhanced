// Recommendations Lifecycle — دورة حياة التوصية: محرّكات (engines) + بدائل مُقيَّمة
// (candidates) + تكييف اقتصاديّ (economic-adaptation) + طبقات القدرة
// (capacity-profiles) + تسجيل النتيجة (outcomes) — كانت نقاط P0 بلا أيّ قارئ في
// الواجهة (UI_DEBT_MAP). صدق: نصوص الخادم العربيّة (agency/honesty/disclaimer)
// تُعرَض حرفيّاً؛ القيمة الغائبة ⇒ «—» لا صفر مُختلق؛ القيمة المجهولة تُلوَّن
// محايدةً لا تُخترَع؛ النتيجة مجهولة حتى تُقاس (outcomes مسار كتابة فقط).
// المصادر: services/sahool-platform/api/routers/recommendations.py +
// core/engines/candidate_generator.py + core/economic_adaptation.py +
// api/recommendations_hub.py (list_engines) + api/api_models.py (OutcomeRecordRequest).

// dash: القيمة الغائبة «—» — نُعيد استخدام المُساعِد القانونيّ نفسه (لا تكرار).
export { dash } from './decisionInsight';

// ── كتالوج المحرّكات (GET /api/v1/recommendations/engines) ──

export interface RecommendationEngine {
  id: string;
  name_ar: string;
  category: string; // irrigation|fertilizer|disease|yield (recommendations_hub.py)
  required_inputs: string[];
  default_enabled: boolean;
}

export interface EnginesResponse {
  engines: RecommendationEngine[];
  policy: unknown | null; // السياسة الخام من settings (أو null = الافتراضيّ)
  effective_enabled: string[]; // المُعرّفات التي ستعمل فعليّاً لهذا المستأجِر
  disabled?: boolean; // 404 ⇒ المسار غير مُفعَّل في هذه البيئة (حالة صادقة)
}

// ── طبقات القدرة (GET /api/v1/recommendations/capacity-profiles) ──

export interface CapacityTierProfile {
  tier: string; // smallholder|mid|commercial
  label_ar: string;
  typical_area_ha: string; // نصّ وصفيّ من الخادم («< 2 هكتار») — يُعرَض حرفيّاً
  investment_posture_ar: string;
  priority_ar: string;
}

export interface CapacityProfilesResponse {
  tiers: CapacityTierProfile[];
  principle_ar?: string;
  disabled?: boolean;
}

// ── البدائل المُقيَّمة (POST /api/v1/recommendations/candidates) ──

/** مكوّن تفكيك الدرجة — known=false يعني قيمة مجهولة عُومِلت محايدةً (تُعلَن). */
export interface CandidateBreakdownComponent {
  value: number;
  weight: number;
  contribution: number;
  source_ar: string;
  known: boolean;
}

export interface ScoredCandidate {
  crop_id: string;
  name_ar: string;
  score: number;
  is_suited: boolean;
  breakdown: Record<string, CandidateBreakdownComponent>;
  flags_ar: string[];
  rank: number;
  highlighted: boolean; // ضمن top_n المُقترَحة — الكلّ يبقى معروضاً (الوكالة)
}

export interface CandidatesResponse {
  goal: string;
  goal_ar: string;
  display_only: boolean;
  total_candidates: number;
  recommended: ScoredCandidate | null;
  candidates: ScoredCandidate[];
  all_options_visible: boolean;
  weights_used: Record<string, number>;
  agency_note_ar: string; // يُعرَض حرفيّاً — اقتراح لا فرض
  honesty_note_ar: string; // يُعرَض حرفيّاً — تقييم حتميّ، لا نموذج يتعلّم
}

/** جسم خيار محصول كما يتوقّعه الخادم (candidate_generator.CropCandidate). */
export interface CropCandidateBody {
  crop_id: string;
  name_ar: string;
  is_suited: boolean;
  water_need_level: string;
  upfront_cost_level: string;
  profit_potential_level: string;
  is_staple: boolean;
  drought_score: number | null;
}

// ── التكييف الاقتصاديّ (POST /api/v1/recommendations/economic-adaptation) ──

export interface EconomicAdaptationResponse {
  display_only: boolean;
  used_in_decision_engine: boolean;
  capacity_tier: string;
  capacity_label_ar: string;
  investment_posture_ar: string;
  economic_priority_ar: string;
  adapted_options: Record<string, unknown>[]; // نفس الخيارات مُرتَّبة — لا حذف
  fit_note_ar: string;
  all_options_visible: boolean;
  agency_note_ar: string; // حرفيّاً
  disclaimer_ar: string; // حرفيّاً — تكييف تقديريّ، لا يَصِم ولا يَحصُر
}

// ── تسجيل النتيجة (POST /api/v1/recommendations/outcomes → 201) ──

/** جسم الطلب — مطابق لـOutcomeRecordRequest (api_models.py): crop+field_id إلزاميّان. */
export interface OutcomeRecordInput {
  crop: string;
  field_id: string;
  farm_id?: string | null;
  season_id?: string | null;
  recommendation_id?: string | null;
  predicted_yield_t_ha?: number | null;
  actual_yield_t_ha?: number | null;
  accepted: boolean;
  matured_within_lag: boolean;
}

export interface OutcomeRecordResult {
  outcome_id: number | string;
  recorded: boolean;
}

// ── أهداف المزارع (FarmerGoal) — التسميات مرآة label_ar في candidate_generator.py ──

export const FARMER_GOALS: readonly { id: string; label_ar: string }[] = [
  { id: 'max_profit', label_ar: 'تعظيم الربح' },
  { id: 'food_security', label_ar: 'الأمن الغذائي' },
  { id: 'min_water', label_ar: 'ترشيد الماء' },
  { id: 'drought_resilience', label_ar: 'الصمود للجفاف' },
] as const;

/** تسمية الهدف — الهدف المجهول يمرّ كما هو من الخادم (لا إخفاء)؛ الغائب «—». */
export function goalLabel(goal: string | null | undefined): string {
  if (!goal) return '—';
  return FARMER_GOALS.find((g) => g.id === goal)?.label_ar ?? goal;
}

// ── مستويات low/mid/high — القيَم التي يفهمها الخادم (_LEVEL في candidate_generator) ──

export const LEVELS: readonly string[] = ['low', 'mid', 'high'] as const;

const LEVEL_AR: Record<string, string> = {
  low: 'منخفض',
  mid: 'متوسّط',
  high: 'مرتفع',
  unknown: 'مجهول', // profit_potential_level الافتراضيّ — يُعلَن لا يُخفى
};

/** تسمية المستوى — القيمة غير المعروفة تمرّ كما هي (الخادم يعاملها «مجهولة محايدة»). */
export function levelLabel(level: string | null | undefined): string {
  if (level == null || level === '') return '—';
  return LEVEL_AR[level] ?? level;
}

// ── فئات المحرّكات — الفئات الموثّقة في recommendations_hub.py:47؛ المجهول محايد ──

const ENGINE_CATEGORY_AR: Record<string, string> = {
  irrigation: 'ريّ',
  fertilizer: 'تسميد',
  disease: 'أمراض',
  yield: 'غلّة',
};

export function engineCategoryLabel(category: string | null | undefined): string {
  if (!category) return '—';
  return ENGINE_CATEGORY_AR[category] ?? category;
}

// ألوان الفئات المعروفة فقط — المجهولة رماديّ محايد (لا اختراع لون).
const ENGINE_CATEGORY_COLOR: Record<string, string> = {
  irrigation: '#7dd3fc',
  fertilizer: '#86efac',
  disease: '#fca5a5',
  yield: '#fde68a',
};

export function engineCategoryColor(category: string | null | undefined): string {
  return category ? (ENGINE_CATEGORY_COLOR[category] ?? '#64748b') : '#64748b';
}

/** هل المحرّك ضمن المُفعَّلة فعليّاً لهذا المستأجِر (effective_enabled من الخادم)؟ */
export function isEngineEffective(engineId: string, effective: string[] | null | undefined): boolean {
  return (effective ?? []).includes(engineId);
}

export function engineStatusLabel(effective: boolean): string {
  return effective ? 'يعمل فعليّاً' : 'غير مُفعَّل بالسياسة';
}

export function engineStatusColor(effective: boolean): string {
  return effective ? '#86efac' : '#64748b';
}

// ── درجة البديل — تُعرَض كما أرسلها الخادم (مُقرَّبة خادميّاً) ──

/** الدرجة كما أرسلها الخادم — غير العدد الصالح ⇒ «—» (لا نُفبرِك صفراً). */
export function scoreLabel(score: number | null | undefined): string {
  if (typeof score !== 'number' || !Number.isFinite(score)) return '—';
  return String(score);
}

export function suitedLabel(isSuited: boolean | null | undefined): string {
  if (isSuited === true) return 'مناسب إقليميّاً';
  if (isSuited === false) return 'غير مناسب إقليميّاً';
  return '—';
}

export function suitedColor(isSuited: boolean | null | undefined): string {
  if (isSuited === true) return '#86efac';
  if (isSuited === false) return '#fdba74'; // معروض للوكالة، مُرتَّب أدنى — تحذير لا خطأ
  return '#64748b';
}

// ── مسوّدات مُدخلات الخيارات (نصوص نموذج) → أجسام الخادم ──

/** مسوّدة خيار محصول كما يحرّرها المستخدم (drought_score نصّ حرّ يُتحقَّق منه). */
export interface CandidateDraft {
  crop_id: string;
  name_ar: string;
  is_suited: boolean;
  water_need_level: string;
  upfront_cost_level: string;
  profit_potential_level: string;
  is_staple: boolean;
  drought_score: string; // '' = غير مقيس ⇒ null (الخادم يعامله محايداً ويُعلِنه)
}

export function emptyCandidateDraft(): CandidateDraft {
  return {
    crop_id: '',
    name_ar: '',
    is_suited: false, // الافتراضيّ الحذر — لا نفترض ملاءمة غير موثّقة
    water_need_level: 'mid',
    upfront_cost_level: 'mid',
    profit_potential_level: 'unknown', // صدق: الربح مجهول حتى يُوثَّق
    is_staple: false,
    drought_score: '',
  };
}

/** تحقّق مسوّدات الخيارات — مرآة رفضات الخادم 422 (crop_id إلزاميّ، drought_score
 *  رقم في [0,1] إن وُجد). يُعيد رسالة عربيّة أو null عند الصلاح. */
export function validateCandidateDrafts(drafts: CandidateDraft[]): string | null {
  if (drafts.length === 0) return 'أضِف خياراً واحداً على الأقلّ (crop_id إلزاميّ)';
  for (const d of drafts) {
    if (!d.crop_id.trim()) return 'كلّ خيار يجب أن يحمل مُعرّف محصول (crop_id)';
    const s = d.drought_score.trim();
    if (s !== '') {
      const n = Number(s);
      if (!Number.isFinite(n) || n < 0 || n > 1) {
        return `درجة تحمّل الجفاف لـ«${d.crop_id.trim()}» يجب أن تكون رقماً في [0,1] أو تُترَك فارغة`;
      }
    }
  }
  return null;
}

/** يبني أجسام الخادم من المسوّدات — '' في drought_score ⇒ null (غير مقيس، لا اختراع). */
export function buildCandidateBodies(drafts: CandidateDraft[]): CropCandidateBody[] {
  return drafts.map((d) => {
    const s = d.drought_score.trim();
    return {
      crop_id: d.crop_id.trim(),
      // الخادم يعوّض name_ar الغائب بـcrop_id — نطبّق نفس المنطق صراحةً
      name_ar: d.name_ar.trim() || d.crop_id.trim(),
      is_suited: d.is_suited,
      water_need_level: d.water_need_level,
      upfront_cost_level: d.upfront_cost_level,
      profit_potential_level: d.profit_potential_level,
      is_staple: d.is_staple,
      drought_score: s === '' ? null : Number(s),
    };
  });
}

// ── مسوّدة تسجيل النتيجة (نصوص نموذج) → جسم الخادم ──

export interface OutcomeDraft {
  crop: string;
  field_id: string;
  farm_id: string;
  season_id: string;
  recommendation_id: string;
  predicted_yield: string; // نصّ حرّ — يُتحقَّق أنّه رقم ≥ 0 أو فارغ
  actual_yield: string;
  accepted: boolean;
  matured_within_lag: boolean;
}

export function emptyOutcomeDraft(): OutcomeDraft {
  return {
    crop: '', field_id: '', farm_id: '', season_id: '', recommendation_id: '',
    predicted_yield: '', actual_yield: '', accepted: false, matured_within_lag: false,
  };
}

/** رقم غلّة من نصّ: '' ⇒ null (غير مقيس)؛ غير الرقم/السالب ⇒ undefined (رفض). */
function yieldOrNull(s: string): number | null | undefined {
  const t = s.trim();
  if (t === '') return null;
  const n = Number(t);
  if (!Number.isFinite(n) || n < 0) return undefined;
  return n;
}

/** تحقّق مسوّدة النتيجة — مرآة قواعد الخادم (crop+field_id إلزاميّان — api_models.py؛
 *  matured_within_lag=true يستلزم actual_yield_t_ha — recommendations.py). */
export function validateOutcomeDraft(d: OutcomeDraft): string | null {
  if (!d.crop.trim()) return 'المحصول (crop) إلزاميّ — سياق التوصية';
  if (!d.field_id.trim()) return 'مُعرّف الحقل (field_id) إلزاميّ — سياق التوصية';
  if (yieldOrNull(d.predicted_yield) === undefined) return 'الغلّة المتوقَّعة يجب أن تكون رقماً ≥ 0 أو تُترَك فارغة';
  if (yieldOrNull(d.actual_yield) === undefined) return 'الغلّة الفعليّة يجب أن تكون رقماً ≥ 0 أو تُترَك فارغة';
  if (d.matured_within_lag && yieldOrNull(d.actual_yield) === null) {
    return 'النضج ضمن المهلة يستلزم غلّة فعليّة مقيسة — لا نتيجة بلا قياس';
  }
  return null;
}

/** يبني جسم الخادم من مسوّدة صالحة — الحقل الاختياريّ الفارغ ⇒ null (لا اختراع). */
export function buildOutcomeInput(d: OutcomeDraft): OutcomeRecordInput {
  return {
    crop: d.crop.trim(),
    field_id: d.field_id.trim(),
    farm_id: d.farm_id.trim() || null,
    season_id: d.season_id.trim() || null,
    recommendation_id: d.recommendation_id.trim() || null,
    predicted_yield_t_ha: yieldOrNull(d.predicted_yield) ?? null,
    actual_yield_t_ha: yieldOrNull(d.actual_yield) ?? null,
    accepted: d.accepted,
    matured_within_lag: d.matured_within_lag,
  };
}
