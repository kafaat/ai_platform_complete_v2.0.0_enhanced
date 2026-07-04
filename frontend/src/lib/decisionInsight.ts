// Decision Insight — رؤى القرار المُدام: سجلّ القرارات (decision_record v78) + سلسلة
// الشرح (explain: ثقة → إشارات → سياسة → قيود → إجراء) + اقتراحات التعلُّم المُسنَدة
// بالأثر + الأثر المُحقَّق — كانت مسارات قراءة بلا أيّ قارئ في الواجهة. صدق: أحكام
// الخادم تمرّ كما هي (calibrated=false يُعرَض لا يُخفى، advisory_only يُعلَن)؛ القيمة
// الغائبة ⇒ «—» لا صفر مُختلق؛ الكتلة الغائبة (present=false) تُسقَط من سلسلة الشرح
// لا تُفبرَك. الميزات خلف أعلام (FEATURE_DECISION_STUDIO / SAHOOL_DECISION_DISPATCH)
// — 404 ⇒ حالة «غير مفعّلة» صادقة.

// ── سجلّ القرارات المُدامة (GET /api/v1/decision/records) ──

export interface DecisionRecord {
  decision_id: string;
  field_id: string | null;
  decision_type: string;
  region: string | null;
  stage: string;
  decision_value: Record<string, unknown>;
  confidence: number | null;
  created_by: string | null;
  created_at: string | null;
}

export interface DecisionRecordsResponse {
  decisions: DecisionRecord[];
  count: number;
  disabled?: boolean;
}

// ── شرح القرار (GET /api/v1/decision/{decision_id}/explain) ──

export interface ExplainConfidence {
  value: number | null;
  data_quality: unknown;
  present: boolean;
}

export interface ExplainRisk {
  key: string | null;
  label_ar: string | null;
  level_ar: string | null;
}

export interface ExplainSignals {
  water: { present: boolean; needs_irrigation: boolean | null; depletion_mm: number | null; deficit_mm: number | null };
  nutrient: { present: boolean; stage: string | null; remaining_need_kg_ha: number | null };
  phenology: { present: boolean; stage: string | null; past_maturity: boolean | null };
  risks: ExplainRisk[];
  stress_flags: { code: string | null; label_ar: string | null }[];
}

export interface ExplainPolicy {
  present: boolean;
  resolved: string | null;
  applied: string | null;
  auto: boolean | null;
  reasons_ar: string[];
}

export interface ExplainConstraints {
  max_application_mm: number | null;
  season_budget_mm: number | null;
  budget_exhausted: boolean | null;
  active_risks: ExplainRisk[];
  economic_status: string | null;
}

export interface ExplainFinal {
  present: boolean;
  recommended_action: string | null;
  next_event_mm: number | null;
  total_irrigation_mm: number | null;
  next_event_day: number | string | null;
  dynamic_kc: unknown;
  fertilization: { present: boolean; due: boolean | null; action_ar: string | null };
}

export interface DecisionExplanation {
  crop: string | null;
  crop_known: boolean;
  decision_id: string | null;
  field_id: string | null;
  confidence: ExplainConfidence;
  signals: ExplainSignals;
  policy: ExplainPolicy;
  constraints: ExplainConstraints;
  final: ExplainFinal;
  calibrated: boolean; // false دائماً من الخادم — مشتقّ من قرار غير معايَر (يُعرَض لا يُخفى)
  has_decision_value: boolean;
}

/** نتيجة مُدامة مربوطة بالقرار (replay: ماذا حدث فعلاً) — outcome_record v79. */
export interface PersistedOutcome {
  outcome_id: string;
  decision_id: string | null;
  field_id: string | null;
  region: string | null;
  stage: string;
  planned: Record<string, unknown> | null;
  actual: Record<string, unknown> | null;
  metrics: Record<string, unknown> | null;
  success: boolean | null; // NULL من الخادم = لا حكم (لا مقياس مُقيَّم) — لا يُفبرَك
  created_by: string | null;
  created_at: string | null;
}

export interface DecisionExplainResponse {
  decision_id: string;
  decision_type?: string;
  field_id?: string | null;
  region?: string | null;
  confidence?: number | null;
  created_at?: string | null;
  explanation: DecisionExplanation | null; // null ⇒ الميزة مُطفأة/القرار غير مُدام (404 صادق)
  outcomes: PersistedOutcome[];
  outcome_count: number;
  evidence?: Record<string, unknown> | null;
  calibrated: boolean;
  disabled?: boolean;
}

// ── اقتراحات التعلُّم (GET /api/v1/decision/learning) — استشاريّة، لا تُطبَّق آليّاً ──

export interface LearningSuggestion {
  kind: 'raise_approvals' | 'relax_friction' | 'favor_water_efficiency' | 'review_failures' | string;
  action_type: string;
  message_ar: string;
  evidence: {
    executed: number;
    failed: number;
    sample: number;
    success_rate: number;
    water_saved_mm: number;
  };
  confidence: number; // [0,1] — يتزايد مع العيّنة (تشبع عند 30)
}

export interface DecisionLearningResponse {
  suggestions: LearningSuggestion[];
  count: number;
  advisory_only: boolean; // true من الخادم — human-in-the-loop (يُعلَن في الواجهة)
  based_on: { total_decisions: number; min_sample: number } | null;
  disabled?: boolean;
}

// ── الأثر المُحقَّق (GET /api/v1/decision/impact) — قياس ما حدث، لا تنبّؤ ──

export interface ImpactByAction {
  executed: number;
  failed: number;
  water_saved_mm: number;
}

export interface DecisionImpactResponse {
  total_decisions: number;
  executed: number;
  failed: number;
  success_rate: number; // executed / (executed+failed) — [0,1]
  water_requested_mm: number;
  water_applied_mm: number;
  water_saved_mm: number;
  water_records: number; // السجلّات التي أُحتسب لها الماء (شفافيّة التغطية)
  by_action: Record<string, ImpactByAction>;
  disabled?: boolean;
}

// ── مُساعِدات عرض نقيّة — الغائب «—» لا صفر مُختلق ──

/** قيمة للعرض: null/undefined/فراغ ⇒ «—» (الصفر قيمة حقيقيّة تُعرَض، لا تُسقَط). */
export function dash(v: string | number | null | undefined): string {
  return v === null || v === undefined || v === '' ? '—' : String(v);
}

/** نسبة [0,1] ⇒ «72٪» — غير العدد الصالح ⇒ «—» (لا نُفبرِك صفراً). */
export function percentLabel(v: number | null | undefined): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
  return `${Math.round(v * 100)}٪`;
}

const DECISION_TYPE_AR: Record<string, string> = {
  crop_twin: 'توأم المحصول',
  irrigation_plan: 'خطّة الريّ',
  profit_aware: 'قرار واعٍ بالربح',
  unified: 'قرار موحّد',
};

/** تسمية نوع القرار — النوع المجهول يمرّ كما هو من الخادم (لا إخفاء). */
export function decisionTypeLabel(type: string | null | undefined): string {
  return type ? (DECISION_TYPE_AR[type] ?? type) : '—';
}

const SUGGESTION_KIND_AR: Record<string, string> = {
  raise_approvals: 'رفع الموافقات',
  relax_friction: 'تخفيف الاحتكاك',
  favor_water_efficiency: 'ترجيح كفاءة الماء',
  review_failures: 'مراجعة الإخفاقات',
};

export function suggestionKindLabel(kind: string | null | undefined): string {
  return kind ? (SUGGESTION_KIND_AR[kind] ?? kind) : '—';
}

// حذر برتقاليّ/أحمر، ثقة خضراء، كفاءة ماء زرقاء — المجهول محايد.
const SUGGESTION_KIND_TONE: Record<string, string> = {
  raise_approvals: '#fdba74',
  review_failures: '#fca5a5',
  relax_friction: '#86efac',
  favor_water_efficiency: '#7dd3fc',
};

export function suggestionKindColor(kind: string | null | undefined): string {
  return kind ? (SUGGESTION_KIND_TONE[kind] ?? '#64748b') : '#64748b';
}

// ── سلسلة الشرح للعرض — الكتلة الغائبة (present=false) تُسقَط لا تُفبرَك ──

export interface ExplanationStep {
  key: 'confidence' | 'signals' | 'policy' | 'constraints' | 'final';
  label_ar: string;
  detail_ar: string;
}

/** يحوّل سلسلة الشرح المُهيكَلة إلى خطوات عرض مرتّبة (ثقة → إشارات → سياسة → قيود
 *  → إجراء). صدق: كتلة غائبة/فارغة تُسقَط كلّيّاً — لا خطوة مُختلقة لغياب. */
export function explanationSteps(exp: DecisionExplanation | null | undefined): ExplanationStep[] {
  if (!exp) return [];
  const steps: ExplanationStep[] = [];

  if (exp.confidence?.present) {
    steps.push({ key: 'confidence', label_ar: 'الثقة', detail_ar: percentLabel(exp.confidence.value) });
  }

  const sig = exp.signals;
  if (sig) {
    const parts: string[] = [];
    if (sig.water?.present) parts.push(sig.water.needs_irrigation ? 'الماء: يحتاج ريّاً' : 'الماء: مكتفٍ');
    if (sig.phenology?.present && sig.phenology.stage != null) parts.push(`الطور: ${sig.phenology.stage}`);
    if (sig.nutrient?.present && sig.nutrient.stage != null) parts.push(`التغذية: ${sig.nutrient.stage}`);
    if ((sig.stress_flags ?? []).length > 0) parts.push(`أعلام إجهاد: ${sig.stress_flags.length}`);
    if (parts.length > 0) steps.push({ key: 'signals', label_ar: 'الإشارات', detail_ar: parts.join(' · ') });
  }

  if (exp.policy?.present) {
    steps.push({ key: 'policy', label_ar: 'السياسة', detail_ar: dash(exp.policy.applied ?? exp.policy.resolved) });
  }

  const con = exp.constraints;
  if (con) {
    const parts: string[] = [];
    if (con.season_budget_mm != null) parts.push(`ميزانيّة الموسم ${con.season_budget_mm}مم`);
    if (con.max_application_mm != null) parts.push(`سقف التطبيق ${con.max_application_mm}مم`);
    if (con.budget_exhausted === true) parts.push('الميزانيّة مستنفَدة');
    if ((con.active_risks ?? []).length > 0) parts.push(`مخاطر فاعلة: ${con.active_risks.length}`);
    if (parts.length > 0) steps.push({ key: 'constraints', label_ar: 'القيود', detail_ar: parts.join(' · ') });
  }

  const fin = exp.final;
  if (fin?.present) {
    const parts: string[] = [];
    if (fin.recommended_action) parts.push(fin.recommended_action);
    if (fin.next_event_mm != null) parts.push(`الحدث التالي ${fin.next_event_mm}مم`);
    if (fin.total_irrigation_mm != null) parts.push(`إجماليّ الريّ ${fin.total_irrigation_mm}مم`);
    if (fin.fertilization?.present && fin.fertilization.action_ar) parts.push(fin.fertilization.action_ar);
    steps.push({ key: 'final', label_ar: 'الإجراء', detail_ar: parts.length > 0 ? parts.join(' · ') : '—' });
  }

  return steps;
}

/** حكم نتيجة مُدامة (success من الخادم): true/false/NULL — NULL «بلا حكم» صادق. */
export function outcomeSuccessLabel(success: boolean | null | undefined): string {
  if (success === true) return 'نجح';
  if (success === false) return 'انحرف';
  return 'بلا حكم';
}

export function outcomeSuccessColor(success: boolean | null | undefined): string {
  if (success === true) return '#86efac';
  if (success === false) return '#fca5a5';
  return '#64748b';
}
