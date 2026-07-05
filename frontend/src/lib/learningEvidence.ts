// Learning & Evidence — يعكس نقاط backend اليتيمة (P3، سطح المرشد الزراعيّ) عن الواجهة.
// هذه المجموعة أسطح «تعلّم/دليل/حوكمة» إرشاديّة صرفة — لا تُصدِر توصية مُلزِمة:
//   GET  /api/v1/learning/activation-status        (بوّابة تفعيل التعلّم — core.learning_activation)
//   POST /api/v1/learning/external-prior-blend      (مزج سابقة خارجيّة — core.engines.external_prior_blend)
//   GET  /api/v1/learning/prediction-calibration    (معايرة التنبّؤ — core.learning.prediction_calibration)
//   GET  /api/v1/policy-learning/threshold-suggestions (اقتراح عتبات — core.policy_learning)
//   POST /api/v1/calibration/feedback               (تغذية راجعة معايرة — api.learning_feedback)
//   POST /api/v1/observations                       (تسجيل مشاهدة — core.offline_first، كتابة)
//   GET  /api/v1/indicators/map-layers              (طبقات الخريطة — analytics_shapers)
//   GET  /api/v1/indices/coverage-report            (تغطية المؤشّرات — spectral_stress_bridge)
//   POST /api/v1/evidence/corroborate               (تظافر القرائن — api.evidence_corroboration)
//   POST /api/v1/confidence-gate                    (بوّابة الثقة — api.confidence_gate)
//
// صدق صارم (نفس عرف irrigationDecisionAids.ts/agroAnalytics.ts): كلّ الأحكام والنصوص من
// الخادم تمرّ حرفيّاً (reason_ar/note_ar/honesty_note_ar/rationale_ar/nudge_ar/warnings_ar…)
// — لا يُعاد الحكم في الواجهة. أعلام الحوكمة (auto_adjust=false/calibrated=false/can_activate)
// تُعرَض كما جاءت دون تجميل. null/غائب ⇒ «—» أو يسقط (لا تصفير ولا تلفيق). خرائط القيم
// المعروفة هنا للتلوين/التسمية العرضيّة فقط؛ القيمة المجهولة ⇒ محايد يمرّ نصّها كما هو.

// ── ألوان وسوم عرضيّة (نفس لوحة AgroAnalyticsCard/approvalsConsole) ─────────────
const DASH = '—';
const OK = '#86efac';
const WARN = '#fdba74';
const DANGER = '#fca5a5';
const INFO = '#7dd3fc';
const NEUTRAL = '#64748b';

export interface Badge {
  label_ar: string;
  color: string;
}
export interface Fact {
  label: string;
  value: string;
}

// ── تنسيق وتحليل مُدخلات (بلا حكم) ─────────────────────────────────────────────

/** تنسيق رقم للعرض — null/undefined/غير منتهٍ ⇒ «—» (لا تصفير). */
export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return v.toFixed(digits);
}

/** كسر الخادم على [0,1] ⇒ نصّ نسبة مئويّة؛ الغائب ⇒ «—» (لا تصفير). */
export function pctFromFraction(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return `${(v * 100).toFixed(digits)}٪`;
}

/** يحلّل نصّ إدخال المستخدم إلى رقم — فارغ/غير رقميّ ⇒ null (لا افتراض قيمة). */
export function parseMeasure(text: string): number | null {
  const t = text.trim();
  if (t === '') return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

// ═══ 1) بوّابة تفعيل التعلّم — GET /api/v1/learning/activation-status ═══════════
/** core.learning_activation.evaluate_activation + أعلام الربط الحيّ. */
export interface ActivationStatus {
  tenant_id?: string;
  state?: string; // dormant | accumulating | ready
  state_ar?: string;
  progress_pct?: number;
  completed_outcomes?: number;
  threshold?: number;
  acceptance_rate?: number;
  lag_compliance?: number;
  blockers?: string[];
  can_activate?: boolean;
  honesty_note_ar?: string;
  schema_ready?: boolean;
  live_data_wired?: boolean;
  data_source_note_ar?: string;
  disabled?: boolean;
}

/** حالة البوّابة (dormant/accumulating/ready) — لون فقط؛ النصّ state_ar من الخادم. */
const ACTIVATION_STATES: Record<string, Badge> = {
  dormant: { label_ar: 'خاملة', color: NEUTRAL },
  accumulating: { label_ar: 'تتراكم', color: WARN },
  ready: { label_ar: 'جاهزة', color: OK },
  active: { label_ar: 'مُفعَّلة', color: OK },
};
export function activationBadge(state: string | null | undefined): Badge {
  const known = state != null ? ACTIVATION_STATES[state.toLowerCase()] : undefined;
  return known ?? { label_ar: state ?? DASH, color: NEUTRAL };
}

/** حقائق عرض البوّابة (تُسقِط الغائب — لا تصفير). */
export function activationFacts(data: ActivationStatus | null | undefined): Fact[] {
  if (!data) return [];
  const out: Fact[] = [];
  if (data.completed_outcomes != null && data.threshold != null) {
    out.push({ label: 'نتائج مكتملة', value: `${data.completed_outcomes}/${data.threshold}` });
  }
  if (data.progress_pct != null) out.push({ label: 'التقدّم', value: `${fmtNum(data.progress_pct, 1)}٪` });
  if (data.acceptance_rate != null) out.push({ label: 'القبول', value: pctFromFraction(data.acceptance_rate) });
  if (data.lag_compliance != null) out.push({ label: 'النضج الزمنيّ', value: pctFromFraction(data.lag_compliance) });
  return out;
}

// ═══ 2) مزج سابقة خارجيّة — POST /api/v1/learning/external-prior-blend ═══════════
/** إشارة تصعيد بشريّ مُضمَّنة (human_escalation.assess_escalation). */
export interface EscalationInfo {
  level?: string; // none | review | blocked
  priority?: string;
  reason_ar?: string;
  recipient_role_ar?: string;
  uncertain_points_ar?: string[];
  honesty_note_ar?: string;
}
/** core.engines.external_prior_blend.blend_external_prior. */
export interface ExternalPriorBlend {
  applicable?: boolean;
  blended_estimate?: number | null;
  local_estimate?: number | null;
  external_prior?: number | null;
  n_local?: number;
  local_weight?: number;
  external_weight?: number;
  external_credibility?: number;
  output_confidence?: number;
  prior_faded?: boolean;
  matured?: boolean;
  escalation?: EscalationInfo;
  reason_ar?: string;
  honesty_note_ar?: string;
  disabled?: boolean;
}
/** جسم POST external-prior-blend (ExternalPriorBlendRequest). */
export interface ExternalPriorBlendInput {
  external_prior: number | null;
  local_estimate: number | null;
  n_local: number;
  crop_grown_in_yemen: boolean;
  external_credibility: number;
}

/** لا نستدعي المزج بلا قرينة واحدة على الأقلّ (سابقة خارجيّة أو تقدير محلّي بعيّنة) —
 *  الخادم يقبل الفراغ ويُصعّده، لكن لا معنى لسؤال بلا مُدخل (تجنّب استدعاء عبثيّ). */
export function blendReady(input: ExternalPriorBlendInput | null | undefined): boolean {
  if (!input) return false;
  return input.external_prior != null || (input.local_estimate != null && input.n_local > 0);
}

/** حقائق عرض المزج (تُسقِط الغائب؛ الأوزان/الثقة كما حسبها الخادم). */
export function blendFacts(data: ExternalPriorBlend | null | undefined): Fact[] {
  if (!data || data.applicable === false || data.blended_estimate == null) return [];
  const out: Fact[] = [
    { label: 'التقدير الممزوج', value: fmtNum(data.blended_estimate, 3) },
  ];
  if (data.local_weight != null) out.push({ label: 'وزن محلّيّ', value: fmtNum(data.local_weight, 2) });
  if (data.external_weight != null) out.push({ label: 'وزن خارجيّ', value: fmtNum(data.external_weight, 2) });
  if (data.output_confidence != null) out.push({ label: 'ثقة المخرَج', value: pctFromFraction(data.output_confidence) });
  if (data.n_local != null) out.push({ label: 'عيّنات محلّيّة', value: `${data.n_local}` });
  return out;
}

// ═══ 3) معايرة التنبّؤ — GET /api/v1/learning/prediction-calibration ═════════════
/** core.learning.prediction_calibration.analyze_systematic_bias + أعلام الربط. */
export interface PredictionCalibration {
  bias_type?: string; // overprediction | underprediction | unbiased | insufficient
  mean_signed_bias?: number;
  n_pairs?: number;
  n_farms?: number;
  confidence_weight?: number;
  correction_factor?: number;
  can_calibrate?: boolean;
  reason_ar?: string;
  honesty_note_ar?: string;
  schema_ready?: boolean;
  live_data_wired?: boolean;
  has_pairs?: boolean;
  data_source_note_ar?: string;
  disabled?: boolean;
}

/** نوع الانحياز — لون/تسمية عرضيّة؛ النصّ reason_ar من الخادم. المجهول محايد. */
const BIAS_TYPES: Record<string, Badge> = {
  overprediction: { label_ar: 'إفراط في التقدير', color: WARN },
  underprediction: { label_ar: 'تقليل التقدير', color: WARN },
  unbiased: { label_ar: 'بلا انحياز منهجيّ', color: OK },
  insufficient: { label_ar: 'عيّنة غير كافية', color: NEUTRAL },
};
export function biasBadge(biasType: string | null | undefined): Badge {
  const known = biasType != null ? BIAS_TYPES[biasType.toLowerCase()] : undefined;
  return known ?? { label_ar: biasType ?? DASH, color: NEUTRAL };
}

/** حقائق معايرة التنبّؤ (تُسقِط الغائب). correction_factor=1.0 يعني «لا تصحيح». */
export function calibrationFacts(data: PredictionCalibration | null | undefined): Fact[] {
  if (!data) return [];
  const out: Fact[] = [];
  if (data.n_pairs != null) out.push({ label: 'أزواج', value: `${data.n_pairs}` });
  if (data.n_farms != null) out.push({ label: 'مزارع', value: `${data.n_farms}` });
  if (data.mean_signed_bias != null) out.push({ label: 'متوسّط الانحياز', value: pctFromFraction(data.mean_signed_bias, 1) });
  if (data.confidence_weight != null) out.push({ label: 'وزن الثقة', value: fmtNum(data.confidence_weight, 2) });
  if (data.correction_factor != null) out.push({ label: 'معامل التصحيح', value: `×${fmtNum(data.correction_factor, 3)}` });
  return out;
}

// ═══ 4) اقتراح عتبات — GET /api/v1/policy-learning/threshold-suggestions ═════════
/** بند اقتراح لنوع تنبيه واحد (core.policy_learning). */
export interface ThresholdSuggestionEntry {
  n?: number;
  useful?: number;
  not_useful?: number;
  useful_rate?: number;
  suggestion?: string; // loosen | tighten | keep
  suggested_overrides?: Record<string, number>;
  threshold_keys?: string[];
  rationale_ar?: string;
}
export interface ThresholdSuggestions {
  min_samples?: number;
  false_positive_rate?: number;
  per_type?: Record<string, ThresholdSuggestionEntry>;
  note_ar?: string;
  outcomes_considered?: number;
  disabled?: boolean;
}
export interface ThresholdSuggestionRow extends ThresholdSuggestionEntry {
  alert_type: string;
}

/** اتّجاه الاقتراح — loosen/tighten/keep (لون/تسمية؛ النصّ rationale_ar من الخادم). */
const SUGGESTIONS: Record<string, Badge> = {
  loosen: { label_ar: 'تقليل الحسّاسيّة', color: WARN },
  tighten: { label_ar: 'زيادة الحسّاسيّة', color: INFO },
  keep: { label_ar: 'أبقِ كما هي', color: OK },
};
export function suggestionBadge(suggestion: string | null | undefined): Badge {
  const known = suggestion != null ? SUGGESTIONS[suggestion.toLowerCase()] : undefined;
  return known ?? { label_ar: suggestion ?? DASH, color: NEUTRAL };
}

/** يُسطّح per_type (قاموس) إلى صفوف مرتّبة بنوع التنبيه — لعرض ثابت مستقرّ. */
export function thresholdSuggestionRows(
  data: ThresholdSuggestions | null | undefined,
): ThresholdSuggestionRow[] {
  const per = data?.per_type;
  if (!per || typeof per !== 'object') return [];
  return Object.keys(per)
    .sort()
    .map((alert_type) => ({ alert_type, ...per[alert_type] }));
}

/** يُسطّح suggested_overrides (KEY→قيمة) إلى مصفوفة لعرض «العتبة المُقترَحة». */
export function overrideEntries(
  overrides: Record<string, number> | null | undefined,
): { key: string; value: number }[] {
  if (!overrides || typeof overrides !== 'object') return [];
  return Object.keys(overrides)
    .sort()
    .map((key) => ({ key, value: overrides[key] }));
}

// ═══ 5) تغذية راجعة المعايرة — POST /api/v1/calibration/feedback ═════════════════
/** بند منطقة واحد (api.learning_feedback._region_feedback). */
export interface RegionFeedback {
  region?: string;
  evidence_level?: string;
  sample_count?: number;
  success_rate?: number | null;
  action?: string; // collect_data | review_calibration | verify | monitor
  priority?: number;
  review_targets?: string[];
  recommendation_ar?: string;
}
export interface CalibrationFeedbackSummary {
  n_regions?: number;
  n_none?: number;
  n_preliminary?: number;
  n_verified?: number;
  mean_success_rate?: number | null;
  regions_needing_data?: string[];
  regions_needing_review?: string[];
}
export interface CalibrationFeedback {
  regions?: RegionFeedback[];
  summary?: CalibrationFeedbackSummary;
  auto_adjust?: boolean; // دائماً false — لا تعديل آليّ (يُعرَض كما هو)
  calibrated?: boolean; // دائماً false — اقتراحات مراجعة بشريّة لا معايرة
  warnings_ar?: string[];
  disabled?: boolean;
}
/** سجلّ دليل منطقة (EvidenceRecord) يبنيه المستخدم لتغذية /feedback. */
export interface EvidenceRecordInput {
  region: string;
  evidence_level: string; // none | field_preliminary | field_verified
  sample_count: number;
  success_rate: number | null;
  samples_to_verified: number;
}

/** إجراء المنطقة — لون/تسمية؛ النصّ recommendation_ar من الخادم. */
const FEEDBACK_ACTIONS: Record<string, Badge> = {
  collect_data: { label_ar: 'اجمع بيانات', color: NEUTRAL },
  review_calibration: { label_ar: 'راجِع المعايرة', color: DANGER },
  verify: { label_ar: 'تحقّق ميدانيّ', color: WARN },
  monitor: { label_ar: 'راقِب فقط', color: OK },
};
export function feedbackActionBadge(action: string | null | undefined): Badge {
  const known = action != null ? FEEDBACK_ACTIONS[action.toLowerCase()] : undefined;
  return known ?? { label_ar: action ?? DASH, color: NEUTRAL };
}

// ═══ 6) تسجيل مشاهدة (كتابة) — POST /api/v1/observations ═════════════════════════
/** ObservationRequest (api_models.py). measured_at ISO؛ value رقميّ من قياس. */
export interface ObservationInput {
  tenant_id: string;
  farm_id: string | null;
  field_id: string | null;
  observable_id: string;
  value: number | null;
  unit: string;
  source: string; // manual | sensor | lab | satellite
  confidence: string; // low | medium | high
  measured_at: string; // ISO datetime
  method: string | null;
}
/** استجابة التسجيل (offline queue) — status/op_id/queued_for_sync/message_ar. */
export interface ObservationResult {
  status?: string;
  op_id?: string;
  queued_for_sync?: boolean;
  message_ar?: string;
}

/** جاهزيّة نموذج المشاهدة: لا إرسال بلا قياس حقيقيّ (observable + قيمة + وقت + مستأجِر). */
export function observationReady(input: ObservationInput | null | undefined): boolean {
  if (!input) return false;
  return (
    !!input.tenant_id &&
    !!input.observable_id.trim() &&
    input.value != null &&
    Number.isFinite(input.value) &&
    !!input.measured_at.trim()
  );
}

// ═══ 7) طبقات الخريطة — GET /api/v1/indicators/map-layers ════════════════════════
/** طبقة خريطة واحدة (analytics_shapers._shape_map_layers). */
export interface MapLayer {
  id?: string;
  name_ar?: string;
  category?: string;
  unit?: string;
  band_math?: string | null;
  source?: string;
  note_ar?: string;
}
export interface MapLayersResponse {
  total?: number;
  layers?: MapLayer[];
  note_ar?: string;
  disabled?: boolean;
}
/** طبقات الخريطة كما جاءت (لا فرز — الخادم مصدر الترتيب). غياب ⇒ []. */
export function mapLayers(data: MapLayersResponse | null | undefined): MapLayer[] {
  return Array.isArray(data?.layers) ? (data?.layers ?? []) : [];
}

// ═══ 8) تقرير تغطية المؤشّرات — GET /api/v1/indices/coverage-report ══════════════
/** spectral_stress_bridge.index_coverage_report: قاموسا وصف نصّيّ عربيّ. */
export interface CoverageReport {
  decision_linked?: Record<string, string>;
  display_or_context_only?: Record<string, string>;
  honesty_note_ar?: string;
  disabled?: boolean;
}
/** يُسطّح قاموس {مؤشّر: وصف} إلى صفوف مرتّبة بالمفتاح (عرض ثابت). */
export function coverageEntries(
  map: Record<string, string> | null | undefined,
): { index: string; desc: string }[] {
  if (!map || typeof map !== 'object') return [];
  return Object.keys(map)
    .sort()
    .map((index) => ({ index, desc: map[index] }));
}

// ═══ 9) تظافر القرائن — POST /api/v1/evidence/corroborate ════════════════════════
/** قرينة واحدة يبنيها المستخدم (EvidenceInput). */
export interface EvidenceItemInput {
  etype: string; // lab_field | regional_prior | remote_sensing | field_obs | historical | crop_model | community_knowledge
  agrees: boolean;
  note_ar: string;
}
/** ملخّص قرينة في الاستجابة (evidence_corroboration). */
export interface EvidenceSummaryItem {
  type_ar?: string;
  agrees?: boolean;
  note_ar?: string;
}
/** corroborate.to_dict() — درجة التوصية بتظافر القرائن. */
export interface CorroborationResult {
  tier?: string; // indicative | corroborated | confirmed
  tier_ar?: string;
  evidence_score?: number;
  n_independent?: number;
  n_agreeing?: number;
  has_field_lab?: boolean;
  nudge_ar?: string | null;
  explanation_ar?: string;
  evidence_summary?: EvidenceSummaryItem[];
  disabled?: boolean;
}
/** جسم POST corroborate. */
export interface CorroborationInput {
  evidences: EvidenceItemInput[];
  recommendation_key: string;
  test_type_ar: string;
}

/** درجة التوصية — لون/تسمية؛ النصّ tier_ar/explanation_ar من الخادم. */
const TIERS: Record<string, Badge> = {
  indicative: { label_ar: 'إرشاديّة', color: NEUTRAL },
  corroborated: { label_ar: 'مؤيَّدة بقرائن', color: INFO },
  confirmed: { label_ar: 'مؤكَّدة مختبريّاً', color: OK },
};
export function tierBadge(tier: string | null | undefined): Badge {
  const known = tier != null ? TIERS[tier.toLowerCase()] : undefined;
  return known ?? { label_ar: tier ?? DASH, color: NEUTRAL };
}

// ═══ 10) بوّابة الثقة — POST /api/v1/confidence-gate ══════════════════════════════
/** إشارة محرّك واحد يبنيها المستخدم (EngineSignalInput). */
export interface EngineSignalInput {
  engine: string;
  has_recommendation: boolean;
  confidence: number | null;
  blocking_reason_ar: string | null;
  data_gaps_ar: string[];
}
/** بند محرّك في الاستجابة (confidence_gate.per_engine). */
export interface PerEngineItem {
  engine?: string;
  has_recommendation?: boolean;
  confidence?: number;
  blocking_reason_ar?: string | null;
  data_gaps_ar?: string[];
}
/** evaluate.to_dict() — قرار بوّابة الثقة الموحّد. */
export interface ConfidenceGateResult {
  decision?: string; // confident | review | blocked
  overall_confidence?: number;
  reason_ar?: string;
  next_action_ar?: string;
  per_engine?: PerEngineItem[];
  disabled?: boolean;
}
export interface ConfidenceGateInput {
  signals: EngineSignalInput[];
}

/** قرار البوّابة — confident/review/blocked (لون/تسمية؛ النصّ reason_ar من الخادم). */
const GATE_DECISIONS: Record<string, Badge> = {
  confident: { label_ar: 'واثقة', color: OK },
  review: { label_ar: 'مراجعة بشريّة', color: WARN },
  blocked: { label_ar: 'محجوبة', color: DANGER },
};
export function gateBadge(decision: string | null | undefined): Badge {
  const known = decision != null ? GATE_DECISIONS[decision.toLowerCase()] : undefined;
  return known ?? { label_ar: decision ?? DASH, color: NEUTRAL };
}

/** مستوى التصعيد المُضمَّن (human_escalation): none/review/blocked. */
const ESCALATION_LEVELS: Record<string, Badge> = {
  none: { label_ar: 'لا تصعيد', color: OK },
  review: { label_ar: 'مراجعة مرشد', color: WARN },
  blocked: { label_ar: 'محجوب (تصعيد حاكم)', color: DANGER },
};
export function escalationBadge(level: string | null | undefined): Badge {
  const known = level != null ? ESCALATION_LEVELS[level.toLowerCase()] : undefined;
  return known ?? { label_ar: level ?? DASH, color: NEUTRAL };
}

// ── خيارات إدخال ثابتة (مفاتيح API التي يعرفها الخادم — التسمية عرض فقط) ─────────
/** أنواع القرائن (evidence_corroboration.EvidenceType) — المفتاح للـAPI. */
export const EVIDENCE_TYPE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'lab_field', label_ar: 'تحليل مختبريّ للحقل' },
  { key: 'regional_prior', label_ar: 'عيّنات مزارع مجاورة' },
  { key: 'remote_sensing', label_ar: 'مؤشّر استشعار (قمر صناعيّ)' },
  { key: 'field_obs', label_ar: 'ملاحظة ميدانيّة' },
  { key: 'historical', label_ar: 'سجلّ مواسم سابقة' },
  { key: 'crop_model', label_ar: 'نموذج حسابيّ (FAO-56)' },
  { key: 'community_knowledge', label_ar: 'معرفة مجتمعيّة/تقويم محلّيّ' },
];
/** محرّكات القرار (confidence_gate docstring) — نصّ حرّ، هذه اقتراحات فقط. */
export const ENGINE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'irrigation', label_ar: 'الريّ' },
  { key: 'nutrient', label_ar: 'التسميد 4R' },
  { key: 'diagnosis', label_ar: 'التشخيص' },
  { key: 'zones', label_ar: 'المناطق' },
];
/** مصدر المشاهدة (ObservationRequest.source). */
export const OBS_SOURCE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'manual', label_ar: 'يدويّ' },
  { key: 'sensor', label_ar: 'مستشعر' },
  { key: 'lab', label_ar: 'مختبر' },
  { key: 'satellite', label_ar: 'قمر صناعيّ' },
];
/** ثقة المشاهدة (ObservationRequest.confidence). */
export const OBS_CONFIDENCE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'low', label_ar: 'منخفضة' },
  { key: 'medium', label_ar: 'متوسّطة' },
  { key: 'high', label_ar: 'عالية' },
];
/** مستوى دليل المنطقة (learning_feedback) لبناء /feedback. */
export const EVIDENCE_LEVEL_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'none', label_ar: 'لا دليل' },
  { key: 'field_preliminary', label_ar: 'أوّليّ ميدانيّ' },
  { key: 'field_verified', label_ar: 'مُتحقَّق ميدانيّاً' },
];
