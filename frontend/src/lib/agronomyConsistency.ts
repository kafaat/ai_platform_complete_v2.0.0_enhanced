// agronomyConsistency — يعكس نقاط backend اليتيمة (P2) بلا قارئ واجهة، طبقة «اتّساق
// القرار الزراعيّ» وما جاورها:
//   GET  /api/v1/consistency/irrigation + /api/v1/consistency/freshness (agronomic_consistency.py)
//   GET  /api/v1/rotation/evaluate + /api/v1/rotation/principles         (crop_rotation.py)
//   GET  /api/v1/wofost/adaptation-guidance + /api/v1/wofost/crop-types  (wofost_crop_params.py)
//   POST /api/v1/reports/operation                                       (reports.py — CSV مدير)
//   POST /api/v1/irrigation-recommendation                              (irrigation_recommendation_policy.py)
//   GET  /api/v1/field/operational-state                                (field_operational_state.py)
//   POST /api/v1/field-portfolio/optimize                               (field_portfolio.py)
//   POST /api/v1/fields/validate-geometry                              (geospatial_integrity.py)
//
// صدق صارم (نفس عرف irrigationDecisionAids/agroAnalytics): الأحكام والنصوص كلّها من
// الخادم وتمرّ حرفيّاً (message_ar/rationale_ar/reasons_ar/rating_ar/note_ar/evidence_ar…)
// — لا يُعاد الحكم في الواجهة. null/غائب ⇒ «—» أو يسقط (لا تصفير ولا تلفيق). خرائط
// القيم المعروفة هنا للتلوين/التسمية العرضيّة فقط؛ القيمة المجهولة ⇒ محايد + نصّ الخادم كما جاء.

// ── أشكال الاستجابة الحقيقيّة كما يعيدها الخادم ─────────────────────────────

/** agronomic_consistency.py — Conflict.to_dict() (يُستخدَم أيضاً في freshness والحالة التشغيليّة). */
export interface AgroConflict {
  rule_id?: string;
  severity?: string; // block | warn | info
  message_ar?: string;
  evidence_ar?: string;
}

/** agronomic_consistency.py — ConsistencyResult.to_dict() (اتّساق الريّ + النضارة). */
export interface ConsistencyResponse {
  consistent?: boolean;
  requires_human_review?: boolean;
  conflict_count?: number;
  checked_rules?: number;
  conflicts?: AgroConflict[];
  note_ar?: string;
  disabled?: boolean;
}

/** crop_rotation.py — evaluate_rotation() (غير معروف ⇒ supported=false + message_ar). */
export interface RotationEvaluateResponse {
  supported?: boolean;
  message_ar?: string;
  previous_crop?: string;
  candidate_crop?: string;
  rating?: string; // good | acceptable | avoid
  rating_ar?: string;
  reasons_ar?: string[];
  disabled?: boolean;
}

/** crop_rotation.py — rotation_principles(): محصول مصنّف في جدول الدورة. */
export interface SupportedCrop {
  crop?: string;
  name_ar?: string;
  family?: string;
  n_effect?: string;
  season?: string;
}
export interface RotationPrinciplesResponse {
  principles_ar?: string[];
  yemen_context_ar?: string;
  supported_crops?: SupportedCrop[];
  disabled?: boolean;
}

/** wofost_crop_params.py — بارامتر تعديل رئيسيّ (المدى/الأساس اختياريّان حسب النوع). */
export interface WofostKeyParam {
  param?: string;
  name_ar?: string;
  note_ar?: string;
  source_ar?: string;
  range?: string;
  default_wheat?: string;
}
/** wofost_crop_params.py — wofost_adaptation_guidance(). */
export interface WofostGuidanceResponse {
  crop?: string;
  crop_recognized?: boolean;
  model_type?: string;
  model_type_ar?: string;
  expected_change_pct?: string;
  typical_validation_r2?: string;
  data_requirement_gb?: string;
  phenology_ar?: string;
  adaptation_summary_ar?: string;
  key_parameters?: WofostKeyParam[];
  base_model_ar?: string;
  disclaimer_ar?: string;
  limitations_ar?: string[];
  disabled?: boolean;
}

/** wofost_crop_params.py — list_supported_crop_types(). */
export interface WofostModelType {
  name_ar?: string;
  change_pct?: string;
  typical_r2?: string;
}
export interface WofostCropTypesResponse {
  model_types?: Record<string, WofostModelType>;
  note_ar?: string;
  disabled?: boolean;
}

/** field_operational_state.py — FieldOperationalState.to_dict(). */
export interface OperationalStateResponse {
  field_id?: string;
  validity?: string; // valid | degraded | conflicted | insufficient
  execution_mode?: string; // auto | human_review | blocked
  confidence_level?: string | null;
  reasons_ar?: string[];
  conflicts?: AgroConflict[];
  freshness_warnings?: AgroConflict[];
  note_ar?: string;
  disabled?: boolean;
}

/** irrigation_recommendation_policy.py — عنصر دليل (source/value/note_ar). */
export interface EvidenceItem {
  source?: string;
  value?: number;
  note_ar?: string;
}
/** irrigation_recommendation_policy.py — recommend_irrigation(). */
export interface IrrigationRecommendationResponse {
  net_irrigation_mm?: number;
  salinity_leaching_mm?: number;
  gross_irrigation_mm?: number;
  irrigation_efficiency?: number;
  salinity_ks?: number;
  policy?: string; // net_only | salinity_adjusted | salinity_with_leaching | blocked_for_review
  requires_expert_review?: boolean;
  urgency?: string;
  timing_ar?: string;
  rationale_ar?: string;
  evidence?: EvidenceItem[];
  disabled?: boolean;
}

/** field_portfolio.py — صفّ حقل في نتيجة التحسين. */
export interface PortfolioFieldResult {
  field_id?: string;
  area_ha?: number;
  water_demand_m3?: number;
  allocated_m3?: number;
  fraction?: number;
  water_productivity?: number | null;
  expected_margin_captured?: number;
  status?: string; // full | partial | unmet
}
/** field_portfolio.py — optimize_field_portfolio(). */
export interface PortfolioOptimizeResponse {
  total_water_m3?: number;
  allocated_m3?: number;
  unallocated_m3?: number;
  total_expected_margin?: number;
  fields?: PortfolioFieldResult[];
  calibrated?: boolean;
  warnings_ar?: string[];
  disabled?: boolean;
}

/** geospatial_integrity.py — مشكلة تحقّق هندسيّ (المخرَج عبر routers/fields.py). */
export interface GeometryIssue {
  severity?: string; // ok | warning | error
  code?: string;
  message_ar?: string;
  hint?: string | null;
}
/** POST /api/v1/fields/validate-geometry — الشكل المُسطَّح من routers/fields.py. */
export interface GeometryValidateResponse {
  valid?: boolean;
  canonical_crs?: string;
  computed_area_ha?: number | null;
  computed_bbox?: number[] | null;
  issues?: GeometryIssue[];
  has_errors?: boolean;
  has_warnings?: boolean;
  disabled?: boolean;
}

export interface DisplayFact {
  label: string;
  value: string;
}

export interface Badge {
  label_ar: string;
  color: string;
}

const DASH = '—';
/** رماديّ محايد للقيم المجهولة — نفس محايد riskColor في approvalsConsole. */
const NEUTRAL = '#64748b';

// ── تنسيق وتحليل مُدخلات (بلا حكم) — نسخ محليّة موحّدة مع libs الجارة ─────────

/** تنسيق رقم للعرض — null/undefined/غير منتهٍ ⇒ «—» (لا تصفير). */
export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return v.toFixed(digits);
}

/** كسر الخادم (0-1) ⇒ نصّ نسبة مئويّة للعرض؛ الغائب ⇒ «—». */
export function pctFromFraction(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return `${(v * 100).toFixed(digits)}٪`;
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

// ── خرائط قيم معروفة (تلوين/تسمية عرضيّة فقط — المجهول محايد + نصّ الخادم) ───

/** يبني badge من خريطة معروفة: المفتاح المجهول/الغائب ⇒ محايد بنصّ الخادم كما جاء. */
function badgeFrom(
  map: Record<string, Badge>,
  key: string | null | undefined,
): Badge {
  const known = key != null ? map[key.toLowerCase()] : undefined;
  if (known) return known;
  return { label_ar: key ?? DASH, color: NEUTRAL };
}

/** شدّة التناقض (agronomic_consistency.ConflictSeverity): block/warn/info. */
const SEVERITY_BADGES: Record<string, Badge> = {
  block: { label_ar: 'حاجب — راجع قبل التنفيذ', color: '#fca5a5' },
  warn: { label_ar: 'تحذير', color: '#fdba74' },
  info: { label_ar: 'ملاحظة', color: '#7dd3fc' },
};
export function conflictSeverityBadge(severity: string | null | undefined): Badge {
  return badgeFrom(SEVERITY_BADGES, severity);
}

/** الحالة التشغيليّة (field_operational_state.DecisionValidity). */
const VALIDITY_BADGES: Record<string, Badge> = {
  valid: { label_ar: 'صالح', color: '#86efac' },
  degraded: { label_ar: 'متدهور', color: '#fdba74' },
  conflicted: { label_ar: 'متناقض', color: '#fca5a5' },
  insufficient: { label_ar: 'بيانات ناقصة', color: '#94a3b8' },
};
export function validityBadge(validity: string | null | undefined): Badge {
  return badgeFrom(VALIDITY_BADGES, validity);
}

/** نمط التنفيذ (field_operational_state.ExecutionMode). */
const EXECUTION_BADGES: Record<string, Badge> = {
  auto: { label_ar: 'تلقائيّ', color: '#86efac' },
  human_review: { label_ar: 'مراجعة بشريّة', color: '#fdba74' },
  blocked: { label_ar: 'محظور', color: '#fca5a5' },
};
export function executionModeBadge(mode: string | null | undefined): Badge {
  return badgeFrom(EXECUTION_BADGES, mode);
}

/** تقييم التعاقب (crop_rotation.evaluate_rotation.rating). النصّ المعروض rating_ar من الخادم. */
const RATING_BADGES: Record<string, Badge> = {
  good: { label_ar: 'جيّد', color: '#86efac' },
  acceptable: { label_ar: 'مقبول', color: '#7dd3fc' },
  avoid: { label_ar: 'يُفضّل تجنّبه', color: '#fca5a5' },
};
export function rotationRatingBadge(rating: string | null | undefined): Badge {
  return badgeFrom(RATING_BADGES, rating);
}

/** سياسة توصية الريّ (irrigation_recommendation_policy.policy). */
const POLICY_BADGES: Record<string, Badge> = {
  net_only: { label_ar: 'صافٍ فقط', color: '#7dd3fc' },
  salinity_adjusted: { label_ar: 'مُعدَّل للملوحة', color: '#fdba74' },
  salinity_with_leaching: { label_ar: 'ملوحة + غسل', color: '#fdba74' },
  blocked_for_review: { label_ar: 'محجوز لمراجعة خبير', color: '#fca5a5' },
};
export function irrigationPolicyBadge(policy: string | null | undefined): Badge {
  return badgeFrom(POLICY_BADGES, policy);
}

/** شدّة مشكلة التحقّق الهندسيّ (geospatial_integrity.ValidationSeverity). */
const GEOMETRY_SEVERITY_BADGES: Record<string, Badge> = {
  ok: { label_ar: 'سليم', color: '#86efac' },
  warning: { label_ar: 'تحذير', color: '#fdba74' },
  error: { label_ar: 'خطأ', color: '#fca5a5' },
};
export function geometryIssueBadge(severity: string | null | undefined): Badge {
  return badgeFrom(GEOMETRY_SEVERITY_BADGES, severity);
}

/** حالة تخصيص الحقل في المحفظة (field_portfolio.status). */
const PORTFOLIO_STATUS_BADGES: Record<string, Badge> = {
  full: { label_ar: 'ريّ كامل', color: '#86efac' },
  partial: { label_ar: 'ريّ جزئيّ', color: '#fdba74' },
  unmet: { label_ar: 'بلا ريّ', color: '#fca5a5' },
};
export function portfolioStatusBadge(status: string | null | undefined): Badge {
  return badgeFrom(PORTFOLIO_STATUS_BADGES, status);
}

// ── مشتقّات عرض من أشكال الخادم (الغائب يسقط، لا يُصفَّر) ──────────────────

/** رسالة الخادم لاستجابة غير مدعومة (supported=false ⇒ message_ar) — تمرّ كما جاءت. */
export function unsupportedMessage(
  resp: { supported?: boolean; message_ar?: string } | null | undefined,
): string | null {
  if (!resp || resp.supported !== false) return null;
  return resp.message_ar ?? null;
}

/** تناقضات فحص الاتّساق كما يعيدها الخادم — بلا مصفوفة ⇒ []. */
export function conflictRows(
  resp: { conflicts?: AgroConflict[] } | null | undefined,
): AgroConflict[] {
  if (!resp || !Array.isArray(resp.conflicts)) return [];
  return resp.conflicts;
}

/** تحذيرات النضارة في الحالة التشغيليّة — بلا مصفوفة ⇒ []. */
export function freshnessWarningRows(
  resp: OperationalStateResponse | null | undefined,
): AgroConflict[] {
  if (!resp || !Array.isArray(resp.freshness_warnings)) return [];
  return resp.freshness_warnings;
}

/** أسباب التعاقب كما يرتّبها الخادم (evaluate_rotation.reasons_ar) — بلا مصفوفة ⇒ []. */
export function rotationReasons(
  resp: RotationEvaluateResponse | null | undefined,
): string[] {
  if (!resp || !Array.isArray(resp.reasons_ar)) return [];
  return resp.reasons_ar;
}

/** محاصيل جدول الدورة المصنّفة (rotation_principles.supported_crops) — بلا مصفوفة ⇒ []. */
export function supportedCropRows(
  resp: RotationPrinciplesResponse | null | undefined,
): SupportedCrop[] {
  if (!resp || !Array.isArray(resp.supported_crops)) return [];
  return resp.supported_crops;
}

/** بارامترات تعديل WOFOST الرئيسيّة (key_parameters) — بلا مصفوفة ⇒ []. */
export function wofostKeyParams(
  resp: WofostGuidanceResponse | null | undefined,
): WofostKeyParam[] {
  if (!resp || !Array.isArray(resp.key_parameters)) return [];
  return resp.key_parameters;
}

export interface WofostModelTypeRow extends WofostModelType {
  key: string;
}
/** أنواع نماذج المحاصيل من قاموس الخادم (crop-types) — بلا قاموس ⇒ []. */
export function wofostModelTypeRows(
  resp: WofostCropTypesResponse | null | undefined,
): WofostModelTypeRow[] {
  const dict = resp?.model_types;
  if (!dict || typeof dict !== 'object') return [];
  return Object.entries(dict).map(([key, v]) => ({ key, ...v }));
}

/** صفوف حقول المحفظة كما يرتّبها الخادم (فحص الحالة/التخصيص) — بلا مصفوفة ⇒ []. */
export function portfolioFieldRows(
  resp: PortfolioOptimizeResponse | null | undefined,
): PortfolioFieldResult[] {
  if (!resp || !Array.isArray(resp.fields)) return [];
  return resp.fields;
}

/** مشكلات التحقّق الهندسيّ كما يعيدها الخادم — بلا مصفوفة ⇒ []. */
export function geometryIssues(
  resp: GeometryValidateResponse | null | undefined,
): GeometryIssue[] {
  if (!resp || !Array.isArray(resp.issues)) return [];
  return resp.issues;
}

/** حقائق توصية الريّ الموحّدة — أرقام الخادم كما هي (mm/كسور)؛ الغائب يسقط. */
export function irrigationRecommendationFacts(
  resp: IrrigationRecommendationResponse | null | undefined,
): DisplayFact[] {
  if (!resp) return [];
  const facts: DisplayFact[] = [];
  if (resp.net_irrigation_mm != null) facts.push({ label: 'الصافي', value: `${fmtNum(resp.net_irrigation_mm, 1)} مم` });
  if (resp.salinity_leaching_mm != null && resp.salinity_leaching_mm > 0) {
    facts.push({ label: 'غسل الملوحة', value: `${fmtNum(resp.salinity_leaching_mm, 1)} مم` });
  }
  if (resp.gross_irrigation_mm != null) facts.push({ label: 'الإجمالي المسحوب', value: `${fmtNum(resp.gross_irrigation_mm, 1)} مم` });
  if (resp.irrigation_efficiency != null) facts.push({ label: 'كفاءة الريّ', value: pctFromFraction(resp.irrigation_efficiency) });
  if (resp.salinity_ks != null) facts.push({ label: 'معامل إجهاد الملوحة Ks', value: fmtNum(resp.salinity_ks, 2) });
  return facts;
}

/** حقائق ملخّص المحفظة — أرقام الخادم (م³/هامش) كما هي؛ الغائب يسقط. */
export function portfolioSummaryFacts(
  resp: PortfolioOptimizeResponse | null | undefined,
): DisplayFact[] {
  if (!resp) return [];
  const facts: DisplayFact[] = [];
  if (resp.total_water_m3 != null) facts.push({ label: 'الماء الكلّيّ', value: `${fmtNum(resp.total_water_m3, 1)} م³` });
  if (resp.allocated_m3 != null) facts.push({ label: 'المُخصَّص', value: `${fmtNum(resp.allocated_m3, 1)} م³` });
  if (resp.unallocated_m3 != null) facts.push({ label: 'غير المُخصَّص', value: `${fmtNum(resp.unallocated_m3, 1)} م³` });
  if (resp.total_expected_margin != null) facts.push({ label: 'الهامش المتوقّع الكلّيّ', value: fmtNum(resp.total_expected_margin, 1) });
  return facts;
}

/** حقائق نتيجة التحقّق الهندسيّ — المساحة/الـbbox/الـCRS المحسوبة؛ الغائب يسقط. */
export function geometryValidationFacts(
  resp: GeometryValidateResponse | null | undefined,
): DisplayFact[] {
  if (!resp) return [];
  const facts: DisplayFact[] = [];
  if (resp.computed_area_ha != null) facts.push({ label: 'المساحة المحسوبة', value: `${fmtNum(resp.computed_area_ha, 2)} هكتار` });
  if (resp.canonical_crs) facts.push({ label: 'النظام المرجعيّ', value: resp.canonical_crs });
  if (Array.isArray(resp.computed_bbox) && resp.computed_bbox.length === 4) {
    facts.push({ label: 'الإطار المحيط', value: resp.computed_bbox.map((n) => fmtNum(n, 3)).join('، ') });
  }
  return facts;
}
