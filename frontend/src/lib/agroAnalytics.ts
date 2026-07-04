// Agro Analytics — يعكس نقاط backend اليتيمة (P1) عن الواجهة، مُكمِّلاً AgroKnowledgeCard
// (تلك تغطّي إكثار/ما بعد الحصاد/بنّ — هذه تغطّي التحليلات الزراعيّة-البيئيّة):
//   POST /api/v1/agro/crop-risk                          (مخاطر المحصول — core.crop_risk)
//   POST /api/v1/agro/crop-rotation                      (ذكاء الدورة — core.crop_rotation_intelligence)
//   POST /api/v1/agro/decision-playbook                  (دليل القرار — core.decision_playbook)
//   GET  /api/v1/agro/kc-timeseries/{field_id}           (سلسلة Kc لحقل — routers/kc_timeseries.py)
//   GET  /api/v1/agro/kc-timeseries/{field_id}/compare   (مقارنة موسمي Kc — core.kc_persistence)
//   POST /api/v1/agro/plant-soil-feedback                (تغذية راجعة نبات-تربة PSFI — core.soil_feedback_proxy)
//   POST /api/v1/agro/season-comparison                  (مقارنة المواسم — core.season_comparison)
//   POST /api/v1/escalation/assess                       (تصعيد الشكّ لإنسان — core.engines.human_escalation)
//   GET  /api/v1/field/{field_id}/lineage                (نسب أصل الحقل — routers/decision_record.py)
//
// صدق صارم (نفس عرف irrigationDecisionAids.ts): الأحكام والنصوص كلّها من الخادم وتمرّ
// حرفيّاً (verdict_ar/reason_ar/evidence_ar/main_judgement…) — لا يُعاد الحكم في الواجهة.
// null/غائب ⇒ «—» أو يسقط (لا تصفير ولا تلفيق). خرائط القيم المعروفة هنا للتلوين/التسمية
// العرضيّة فقط؛ القيمة المجهولة ⇒ محايد مع تمرير نصّ الخادم كما جاء.

// ── أشكال الاستجابة الحقيقيّة كما يعيدها الخادم ─────────────────────────────

/** core/crop_risk.py — CropRisk (asdict). */
export interface CropRisk {
  risk_type?: string; // fungal_disease | heat_stress | frost_damage
  crop?: string;
  severity?: string; // low | moderate | high
  score?: number; // [0,1]
  reason_ar?: string;
}
/** POST /api/v1/agro/crop-risk ⇒ {crop, risks[]}. */
export interface CropRiskResponse {
  crop?: string;
  risks?: CropRisk[];
  disabled?: boolean;
}
/** جسم POST crop-risk (CropRiskRequest). */
export interface CropRiskInput {
  crop: string;
  disease_risk_score: number;
  heat_stress_hours: number;
  frost_risk_hours: number;
  humidity_avg_percent?: number | null;
}

/** core/crop_rotation_intelligence.py — RotationAssessment (asdict). */
export interface RotationAssessment {
  seasons_analyzed?: number;
  rotation_diversity_index?: number; // [0,1]
  legume_ratio?: number; // [0,1]
  cover_crop_ratio?: number; // [0,1]
  intercropping_ratio?: number; // [0,1]
  host_repeat_risk?: number; // [0,1]
  max_consecutive_same?: number;
  rotation_score?: number; // [0,100]
  direction?: string; // positive | negative | neutral
  evidence_ar?: string[];
  verdict_ar?: string;
  disabled?: boolean;
}
/** موسم واحد في تاريخ الدورة (SeasonCropRequest). */
export interface SeasonCropInput {
  season_id: string;
  crop_id: string;
  crop_family?: string | null;
  is_legume?: boolean;
  is_cover_crop?: boolean;
  intercropped_with?: string[];
}

/** core/decision_playbook.py — DecisionPlaybook (asdict). */
export interface DecisionPlaybook {
  main_judgement?: string;
  confidence?: number; // [0,1]
  evidence?: string[];
  do_today?: string[];
  avoid_now?: string[];
  review_after?: string;
  escalate_if?: string[];
  disabled?: boolean;
}
/** إشارة طقس مُولَّدة (WeatherSignalRequest). */
export interface WeatherSignalInput {
  signal_type: string;
  confidence_score?: number;
  payload?: Record<string, unknown>;
}
/** جسم POST decision-playbook (DecisionPlaybookRequest). */
export interface DecisionPlaybookInput {
  crop?: string | null;
  weather_signals?: WeatherSignalInput[];
  crop_risk_inputs?: CropRiskInput | null;
  soil_feedback_inputs?: SoilFeedbackInput | null;
  recommendation_ar?: string | null;
}

/** routers/kc_timeseries.py — صفّ crop_kc_timeseries المُشكَّل. */
export interface KcRow {
  field_id?: string;
  crop_id?: string;
  season_id?: string;
  scenario_type?: string;
  kc_ini?: number | null;
  kc_mid?: number | null;
  kc_end?: number | null;
  kcb_ini?: number | null;
  kcb_mid?: number | null;
  kcb_end?: number | null;
  cfet?: number | null;
  source?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}
export interface KcSeriesResponse {
  field_id?: string;
  count?: number;
  series?: KcRow[];
  disabled?: boolean;
}
/** core/kc_persistence.py — compare_kc_rows: مرحلة واحدة. */
export interface KcStageCompare {
  current?: number | null;
  previous?: number | null;
  delta?: number | null;
  direction?: string; // up | down | flat
}
export interface KcCompareResponse {
  crop_id?: string | null;
  current_season_id?: string | null;
  previous_season_id?: string | null;
  stages?: Record<string, KcStageCompare>; // kc_ini/kc_mid/kc_end
  verdict_ar?: string;
  disabled?: boolean;
}

/** core/soil_feedback_proxy.py — PlantSoilFeedback (asdict). */
export interface PlantSoilFeedback {
  positive_feedback_score?: number; // [0,100]
  negative_feedback_risk?: number; // [0,100]
  pathogen_accumulation_risk?: number; // [0,100]
  microbial_diversity_proxy?: number; // [0,100]
  soil_resilience_score?: number; // [0,100]
  net_feedback?: number; // [-100,100]
  direction?: string; // positive | negative | neutral
  confidence?: number; // [0,1]
  inputs_known?: number;
  drivers_positive_ar?: string[];
  drivers_negative_ar?: string[];
  verdict_ar?: string;
  disabled?: boolean;
}
/** جسم POST plant-soil-feedback (SoilFeedbackInputsRequest) — كلّها اختياريّة (None = مجهول). */
export interface SoilFeedbackInput {
  rotation_diversity?: number | null;
  legume_ratio?: number | null;
  cover_crop_ratio?: number | null;
  host_repeat_risk?: number | null;
  organic_matter_additions_per_yr?: number | null;
  tillage_intensity?: number | null;
  soil_organic_carbon_pct?: number | null;
  salinity_ds_m?: number | null;
  disease_incidents_recent?: number | null;
  synthetic_fertilizer_intensity?: number | null;
}

/** core/season_comparison.py — مقارنة مقياس واحد. */
export interface MetricCompare {
  current?: number;
  previous?: number;
  delta?: number;
  percent_change?: number | null;
  direction?: string; // up | down | flat
  better?: boolean | null;
}
export interface SeasonComparisonResponse {
  current_season_id?: string;
  previous_season_id?: string;
  crop_id?: string;
  metrics?: Record<string, MetricCompare>;
  skipped_metrics?: string[];
  verdict_ar?: string;
  disabled?: boolean;
}
/** مقاييس موسم واحد (SeasonMetricsRequest) — كلّها اختياريّة عدا المعرّفات. */
export interface SeasonMetricsInput {
  season_id: string;
  crop_id: string;
  kc_mid?: number | null;
  yield_t_ha?: number | null;
  water_used_m3?: number | null;
  ndvi_peak?: number | null;
  et0_total_mm?: number | null;
  water_use_efficiency?: number | null;
}

/** core/engines/human_escalation.py — assess_escalation. */
export interface EscalationAssessResponse {
  source?: string;
  needs_escalation?: boolean;
  level?: string; // none | review | blocked
  recipient_role_ar?: string;
  priority?: string; // none | medium | high
  confidence?: number | null;
  uncertain_points_ar?: string[];
  reason_ar?: string;
  honesty_note_ar?: string;
  disabled?: boolean;
}
/** جسم POST escalation/assess (EscalationAssessRequest). */
export interface EscalationAssessInput {
  confidence?: number | null;
  source: string;
  has_answer?: boolean;
  uncertain_points?: string[];
}

/** routers/decision_record.py — _shape_decision_row + outcomes. */
export interface LineageOutcome {
  outcome_id?: string;
  decision_id?: string;
  field_id?: string;
  success?: boolean | null;
  created_at?: string | null;
}
export interface LineageDecision {
  decision_id?: string;
  field_id?: string;
  decision_type?: string;
  region?: string | null;
  stage?: string | null;
  confidence?: number | null;
  created_by?: string | null;
  created_at?: string | null;
  outcomes?: LineageOutcome[];
}
export interface FieldLineageResponse {
  field_id?: string;
  decisions?: LineageDecision[];
  orphan_outcomes?: LineageOutcome[];
  count?: number;
  disabled?: boolean;
}

export interface DisplayFact {
  label: string;
  value: string;
}

const DASH = '—';
/** رماديّ محايد للقيم المجهولة — نفس محايد riskColor في approvalsConsole. */
const NEUTRAL = '#64748b';

// ── تنسيق وتحليل مُدخلات (بلا حكم) ──────────────────────────────────────────

/** تنسيق رقم للعرض — null/undefined/غير منتهٍ ⇒ «—» (لا تصفير). */
export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return v.toFixed(digits);
}

/** درجة الخادم على [0,1] ⇒ نصّ نسبة مئويّة؛ الغائب ⇒ «—». */
export function pctFromFraction(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return `${(v * 100).toFixed(digits)}٪`;
}

/** درجة الخادم على [0,100] ⇒ نصّ «NN/100»؛ الغائب ⇒ «—» (لا تصفير). */
export function scoreOutOf100(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return `${v.toFixed(digits)}/100`;
}

/** يحلّل نصّ إدخال المستخدم إلى رقم — فارغ/غير رقميّ ⇒ null (لا افتراض). */
export function parseMeasure(text: string): number | null {
  const t = text.trim();
  if (t === '') return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

/** إدخال نسبة مئويّة (كما يفكّر المزارع) ⇒ كسر 0-1 (كما يتوقّع الخادم). فارغ ⇒ null. */
export function parsePctToFraction(text: string): number | null {
  const v = parseMeasure(text);
  return v == null ? null : v / 100;
}

// ── خرائط قيم معروفة (تلوين/تسمية عرضيّة فقط — المجهول محايد) ──────────────

/** شدّة CropRisk: low/moderate/high (crop_risk.py). اللون والتسمية عرضيّان؛
 *  السببّ المعروض هو reason_ar من الخادم. المجهول ⇒ محايد يمرّ نصّه حرفيّاً. */
const SEVERITY_LEVELS: Record<string, { label_ar: string; color: string }> = {
  low: { label_ar: 'منخفضة', color: '#86efac' },
  moderate: { label_ar: 'متوسّطة', color: '#fdba74' },
  high: { label_ar: 'عالية', color: '#fca5a5' },
};

export function severityBadge(severity: string | null | undefined): { label_ar: string; color: string } {
  const known = severity != null ? SEVERITY_LEVELS[severity.toLowerCase()] : undefined;
  if (known) return known;
  return { label_ar: severity ?? DASH, color: NEUTRAL };
}

/** نوع خطر المحصول (crop_risk.py risk_type) — تسمية عرضيّة، المجهول يمرّ كما هو. */
const RISK_TYPES_AR: Record<string, string> = {
  fungal_disease: 'مرض فطريّ',
  heat_stress: 'إجهاد حراريّ',
  frost_damage: 'ضرر صقيع',
};

export function riskTypeAr(riskType: string | null | undefined): string {
  if (!riskType) return DASH;
  return RISK_TYPES_AR[riskType] ?? riskType;
}

/** اتّجاه التغذية الراجعة (positive/negative/neutral) — رواية الدورة/PSFI.
 *  الحُكم النصّيّ (verdict_ar) من الخادم؛ هنا لون وتسمية فقط. */
const FEEDBACK_DIRECTIONS: Record<string, { label_ar: string; color: string }> = {
  positive: { label_ar: 'موجبة', color: '#86efac' },
  negative: { label_ar: 'سالبة', color: '#fca5a5' },
  neutral: { label_ar: 'محايدة', color: '#7dd3fc' },
};

export function feedbackDirectionBadge(direction: string | null | undefined): { label_ar: string; color: string } {
  const known = direction != null ? FEEDBACK_DIRECTIONS[direction.toLowerCase()] : undefined;
  if (known) return known;
  return { label_ar: direction ?? DASH, color: NEUTRAL };
}

/** اتّجاه تغيّر مقياس (up/down/flat) — سهم عرضيّ محايد؛ المجهول ⇒ «—». */
const TREND_ARROWS: Record<string, string> = {
  up: '▲',
  down: '▼',
  flat: '▬',
};

export function trendArrow(direction: string | null | undefined): string {
  if (!direction) return DASH;
  return TREND_ARROWS[direction.toLowerCase()] ?? DASH;
}

/** مستوى التصعيد (human_escalation.py): none/review/blocked. النصّ (reason_ar) من
 *  الخادم؛ هنا لون/تسمية فقط. المجهول ⇒ محايد يمرّ حرفيّاً. */
const ESCALATION_LEVELS: Record<string, { label_ar: string; color: string }> = {
  none: { label_ar: 'لا تصعيد', color: '#86efac' },
  review: { label_ar: 'مراجعة مرشد', color: '#fdba74' },
  blocked: { label_ar: 'محجوب (تصعيد حاكم)', color: '#fca5a5' },
};

export function escalationBadge(level: string | null | undefined): { label_ar: string; color: string } {
  const known = level != null ? ESCALATION_LEVELS[level.toLowerCase()] : undefined;
  if (known) return known;
  return { label_ar: level ?? DASH, color: NEUTRAL };
}

/** أولويّة التصعيد (priority): none/medium/high — تسمية عرضيّة، المجهول يمرّ كما هو. */
const PRIORITY_AR: Record<string, string> = {
  none: 'لا شيء',
  medium: 'متوسّطة',
  high: 'عالية',
};

export function priorityAr(priority: string | null | undefined): string {
  if (!priority) return DASH;
  return PRIORITY_AR[priority.toLowerCase()] ?? priority;
}

// ── خيارات إدخال ثابتة (مفاتيح API التي يعرفها الخادم — التسمية عرض فقط) ────

/** ملفّات المحاصيل في crop_risk.py (_CROP_PROFILES) — المفتاح للـAPI، التسمية عرض. */
export const CROP_RISK_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'wheat', label_ar: 'قمح' },
  { key: 'tomato', label_ar: 'طماطم' },
  { key: 'potato', label_ar: 'بطاطس' },
  { key: 'date_palm', label_ar: 'نخيل' },
  { key: 'maize', label_ar: 'ذرة' },
];

/** أنواع الإشارات الصالحة في decision_playbook.py (_VALID_SIGNALS). */
export const WEATHER_SIGNAL_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'spray_window_open', label_ar: 'نافذة رشّ مفتوحة' },
  { key: 'disease_risk_high', label_ar: 'خطر مرض مرتفع' },
  { key: 'frost_imminent', label_ar: 'صقيع وشيك' },
  { key: 'heat_stress', label_ar: 'إجهاد حراريّ' },
  { key: 'trafficability_poor', label_ar: 'صلاحيّة مرور ضعيفة' },
];

/** سيناريوهات Kc في kc_persistence.py (KC_SCENARIOS). */
export const KC_SCENARIO_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'potential', label_ar: 'كامنة (potential)' },
  { key: 'actual', label_ar: 'فعليّة (actual)' },
  { key: 'full_irrigation', label_ar: 'ريّ كامل' },
  { key: 'deficit', label_ar: 'عجز مائيّ' },
];

// ── مشتقّات عرض من أشكال الخادم (الغائب يسقط، لا يُصفَّر) ──────────────────

/** صفوف مخاطر المحصول كما يرتّبها الخادم — بلا مصفوفة ⇒ [] بصدق. */
export function cropRiskRows(resp: CropRiskResponse | null | undefined): CropRisk[] {
  if (!resp || !Array.isArray(resp.risks)) return [];
  return resp.risks;
}

/** حقائق تقييم الدورة الزراعيّة — الغائب يسقط (لا تصفير). */
export function rotationFacts(resp: RotationAssessment | null | undefined): DisplayFact[] {
  if (!resp) return [];
  const facts: DisplayFact[] = [];
  if (resp.seasons_analyzed != null) facts.push({ label: 'مواسم مُحلَّلة', value: fmtNum(resp.seasons_analyzed) });
  if (resp.rotation_score != null) facts.push({ label: 'درجة التناوب', value: scoreOutOf100(resp.rotation_score) });
  if (resp.rotation_diversity_index != null) facts.push({ label: 'مؤشّر التنوّع', value: pctFromFraction(resp.rotation_diversity_index) });
  if (resp.legume_ratio != null) facts.push({ label: 'نسبة البقوليّات', value: pctFromFraction(resp.legume_ratio) });
  if (resp.cover_crop_ratio != null) facts.push({ label: 'نسبة الغطاء', value: pctFromFraction(resp.cover_crop_ratio) });
  if (resp.intercropping_ratio != null) facts.push({ label: 'التحميل البينيّ', value: pctFromFraction(resp.intercropping_ratio) });
  if (resp.host_repeat_risk != null) facts.push({ label: 'خطر تكرار العائل', value: pctFromFraction(resp.host_repeat_risk) });
  if (resp.max_consecutive_same != null) facts.push({ label: 'أطول تكرار متتالٍ', value: fmtNum(resp.max_consecutive_same) });
  return facts;
}

/** حقائق التغذية الراجعة نبات-تربة (PSFI) — الدرجات [0,100] كما يعيدها الخادم. */
export function psfFacts(resp: PlantSoilFeedback | null | undefined): DisplayFact[] {
  if (!resp) return [];
  const facts: DisplayFact[] = [];
  if (resp.positive_feedback_score != null) facts.push({ label: 'تغذية موجبة', value: scoreOutOf100(resp.positive_feedback_score) });
  if (resp.negative_feedback_risk != null) facts.push({ label: 'خطر سالب', value: scoreOutOf100(resp.negative_feedback_risk) });
  if (resp.pathogen_accumulation_risk != null) facts.push({ label: 'تراكم ممرضات', value: scoreOutOf100(resp.pathogen_accumulation_risk) });
  if (resp.microbial_diversity_proxy != null) facts.push({ label: 'تنوّع ميكروبيّ', value: scoreOutOf100(resp.microbial_diversity_proxy) });
  if (resp.soil_resilience_score != null) facts.push({ label: 'مرونة التربة', value: scoreOutOf100(resp.soil_resilience_score) });
  if (resp.net_feedback != null) facts.push({ label: 'الصافي', value: fmtNum(resp.net_feedback, 1) });
  if (resp.confidence != null) facts.push({ label: 'الثقة', value: pctFromFraction(resp.confidence) });
  if (resp.inputs_known != null) facts.push({ label: 'مؤشّرات معروفة', value: fmtNum(resp.inputs_known) });
  return facts;
}

/** صفوف سلسلة Kc التاريخيّة كما يرتّبها الخادم (بالموسم) — بلا مصفوفة ⇒ []. */
export function kcSeriesRows(resp: KcSeriesResponse | null | undefined): KcRow[] {
  if (!resp || !Array.isArray(resp.series)) return [];
  return resp.series;
}

export interface KcStageRow extends KcStageCompare {
  stage: string;
}

/** صفوف مقارنة مراحل Kc (kc_ini/kc_mid/kc_end) بالترتيب — بلا مراحل ⇒ []. */
export function kcCompareStages(resp: KcCompareResponse | null | undefined): KcStageRow[] {
  const stages = resp?.stages;
  if (!stages || typeof stages !== 'object') return [];
  const order = ['kc_ini', 'kc_mid', 'kc_end'];
  const rows: KcStageRow[] = [];
  for (const stage of order) {
    if (stages[stage]) rows.push({ stage, ...stages[stage] });
  }
  // مراحل غير متوقّعة (إن وُجدت مستقبلاً) تُكشَف لا تُخفى.
  for (const [stage, v] of Object.entries(stages)) {
    if (!order.includes(stage)) rows.push({ stage, ...v });
  }
  return rows;
}

export interface MetricRow extends MetricCompare {
  metric: string;
  label_ar: string;
}

/** تسميات مقاييس المقارنة (season_comparison.py) — عرض فقط، المجهول يمرّ كما هو. */
const METRIC_LABELS_AR: Record<string, string> = {
  kc_mid: 'Kc المنتصف',
  yield_t_ha: 'الغلّة (طن/هـ)',
  water_used_m3: 'الماء المستهلَك (م³)',
  ndvi_peak: 'ذروة NDVI',
  et0_total_mm: 'ET₀ الإجماليّ (مم)',
  water_use_efficiency: 'كفاءة استخدام الماء',
};

/** صفوف مقارنة المواسم — يقرأ قاموس metrics كما بناه الخادم؛ بلا قاموس ⇒ []. */
export function seasonMetricRows(resp: SeasonComparisonResponse | null | undefined): MetricRow[] {
  const metrics = resp?.metrics;
  if (!metrics || typeof metrics !== 'object') return [];
  return Object.entries(metrics).map(([metric, v]) => ({
    metric,
    label_ar: METRIC_LABELS_AR[metric] ?? metric,
    ...v,
  }));
}

/** حكم «الأفضل» لمقياس بعد المقارنة (better من الخادم) ⇒ لون/تسمية عرضيّة.
 *  better=null (محايد/ثابت) ⇒ محايد. لا يُعاد الحكم — فقط تلوين علَم الخادم. */
export function betterBadge(better: boolean | null | undefined): { label_ar: string; color: string } {
  if (better === true) return { label_ar: 'تحسّن', color: '#86efac' };
  if (better === false) return { label_ar: 'تراجع', color: '#fca5a5' };
  return { label_ar: DASH, color: NEUTRAL };
}

/** صفوف قرارات نسب أصل الحقل كما يرتّبها الخادم (الأحدث أوّلاً) — بلا مصفوفة ⇒ []. */
export function lineageDecisionRows(resp: FieldLineageResponse | null | undefined): LineageDecision[] {
  if (!resp || !Array.isArray(resp.decisions)) return [];
  return resp.decisions;
}

/** عدّ نتائج قرار (outcomes) — بلا مصفوفة ⇒ 0 بصدق (لا تخمين). */
export function outcomeCount(decision: LineageDecision | null | undefined): number {
  if (!decision || !Array.isArray(decision.outcomes)) return 0;
  return decision.outcomes.length;
}

/** طابع زمنيّ ISO ⇒ تاريخ قصير للعرض (YYYY-MM-DD)؛ الغائب/غير الصالح ⇒ «—». */
export function shortDate(iso: string | null | undefined): string {
  if (!iso || typeof iso !== 'string') return DASH;
  const d = iso.slice(0, 10);
  return d.length === 10 ? d : DASH;
}

/** يجمع أرقام إدخال المستخدم لمقاييس موسم في جسم SeasonMetricsInput — الفارغ يبقى
 *  غائباً (لا تصفير: مقياس بلا قياس لا يُرسَل، فيتجاهله الخادم بأمان). */
export function buildSeasonMetrics(
  seasonId: string,
  cropId: string,
  raw: Record<string, string>,
): SeasonMetricsInput {
  const out: SeasonMetricsInput = { season_id: seasonId, crop_id: cropId };
  const keys: (keyof SeasonMetricsInput)[] = [
    'kc_mid', 'yield_t_ha', 'water_used_m3', 'ndvi_peak', 'et0_total_mm', 'water_use_efficiency',
  ];
  for (const k of keys) {
    const v = parseMeasure(raw[k] ?? '');
    if (v != null) (out[k] as number) = v;
  }
  return out;
}
