// Irrigation Decision Aids — يعكس نقاط backend اليتيمة (docs/api/UI_DEBT_MAP.md — P0/P1) بلا قارئ واجهة:
//   /api/v1/confidence/ndvi + /api/v1/confidence/irrigation   (ثقة القراءة/التوصية — routers/confidence.py)
//   /api/v1/irrigation/moisture-decision + /api/v1/irrigation/soil-types (قرار الرطوبة RWC — soil_moisture_advisor.py)
//   /api/v1/irrigation-method/gross                            (الصافي ⇒ الإجمالي المسحوب — irrigation_method.py)
//   /api/v1/water-sensitivity/crops                            (المحاصيل المدعومة — crop_water_sensitivity.py)
//   /api/v1/soil-sampling/{protocol,depth,subsamples}          (بروتوكول العيّنة — soil_sampling_protocol.py)
//
// صدق صارم: الأحكام والنصوص كلّها من الخادم وتمرّ حرفيّاً (decision_ar/reason_ar/
// disclaimer_ar/rationale_ar/recommendation_ar/note_ar…) — لا يُعاد الحكم في الواجهة.
// null/غائب ⇒ «—» أو يسقط (لا تصفير ولا تلفيق). خرائط القيم المعروفة هنا للتلوين/
// التسمية العرضيّة فقط، والقيمة المجهولة ⇒ محايد مع تمرير نصّ الخادم كما جاء.

// ── أشكال الاستجابة الحقيقيّة كما يعيدها الخادم ─────────────────────────────

/** services/sahool-platform/api/confidence_engine.py — IndicatorConfidence.to_dict() */
export interface ConfidenceComponents {
  cloud?: number | null;
  temporal?: number | null;
  coverage?: number | null;
  source?: number | null;
}

export interface NdviConfidenceResponse {
  indicator?: string;
  value?: number | null;
  confidence?: { score?: number; level?: string; components?: ConfidenceComponents };
  reasons_ar?: string[];
  recommendation_ar?: string;
  /** 404 من الخادم ⇒ الميزة غير مُفعَّلة — حالة صادقة لا خطأ مُفزِع. */
  disabled?: boolean;
}

/** جسم POST /api/v1/confidence/ndvi (api_models.py: NdviConfidenceRequest). */
export interface NdviConfidenceInput {
  ndvi_value: number;
  observation_date: string; // ISO
  field_area_ha: number;
  cloud_pct?: number;
  cloud_shadow_pct?: number;
  cirrus_pct?: number;
  has_ground_truth?: boolean;
}

/** services/sahool-platform/api/confidence_aggregation.py — AggregatedConfidence.to_dict() */
export interface AggregatedConfidenceResponse {
  score?: number;
  level?: string;
  inputs_used?: string[];
  inputs_missing?: string[];
  inputs_degraded?: string[];
  rationale_ar?: string;
  safe_for_action?: boolean;
  disabled?: boolean;
}

/** جسم POST /api/v1/confidence/irrigation (api_models.py: IrrigationConfRequest) — كسور 0-1. */
export interface IrrigationConfidenceInput {
  ndvi_confidence?: number | null;
  et0_confidence?: number | null;
  soil_moisture_confidence?: number | null;
  weather_forecast_confidence?: number | null;
}

/** soil_moisture_advisor.py — irrigation_amount_mm() (يظهر فقط عند decision ∈ irrigate/monitor). */
export interface IrrigationAmount {
  irrigation_mm?: number;
  root_depth_m?: number;
  deficit_vwc?: number;
  theta_fc?: number;
  formula_ar?: string;
  note_ar?: string;
  root_depth_source_ar?: string;
}

/** soil_moisture_advisor.py — irrigation_guidance(): ok=false ⇒ error_ar فقط. */
export interface MoistureDecisionResponse {
  ok?: boolean;
  error_ar?: string;
  vwc?: number;
  vwc_pct?: number;
  rwc?: number;
  rwc_pct?: number;
  fc_ratio_pct?: number;
  fc_ratio_note_ar?: string;
  soil_type_ar?: string;
  theta_fc?: number;
  theta_wp?: number;
  calibrated?: boolean;
  decision?: string; // irrigate | monitor | safe — حكم الخادم
  decision_ar?: string;
  reason_ar?: string;
  disclaimer_ar?: string;
  crop_ar?: string | null;
  growth_stage_ar?: string | null;
  stage_sensitivity_note_ar?: string | null;
  irrigation_amount?: IrrigationAmount;
  method_ar?: string;
  disabled?: boolean;
}

/** soil_moisture_advisor.py — list_soil_types(): قاموس مفاتيح sand/loam/clay. */
export interface SoilTypeRef {
  name_ar?: string;
  theta_s?: number;
  theta_fc?: number;
  theta_wp?: number;
  note_ar?: string;
}
export interface SoilTypesResponse {
  soil_types?: Record<string, SoilTypeRef>;
  note_ar?: string;
  disabled?: boolean;
}

/** irrigation_method.py — POST /gross (calibrated=false دائماً من الخادم). */
export interface GrossIrrigationResponse {
  net_mm?: number;
  gross_mm?: number;
  gross_m3_ha?: number;
  application_efficiency?: number;
  method?: string;
  pressurized?: boolean;
  calibrated?: boolean;
  disabled?: boolean;
}

/** crop_water_sensitivity.py — supported_crops(). */
export interface WaterSensitivityCrop {
  crop: string;
  name_ar?: string;
  drought_tolerance_ar?: string;
  season_ar?: string;
}
export interface WaterSensitivityCropsResponse {
  crops?: WaterSensitivityCrop[];
  disabled?: boolean;
}

/** soil_sampling_protocol.py — subsamples_for_area(): supported=false ⇒ message_ar. */
export interface SamplingSubsamplesResponse {
  supported?: boolean;
  message_ar?: string;
  area_ha?: number;
  subsamples?: number;
  advice_ar?: string;
  principle_ar?: string;
  note_ar?: string;
  disabled?: boolean;
}

/** soil_sampling_protocol.py — sampling_depth(). */
export interface DepthPurposeRow {
  purpose?: string;
  depth_ar?: string;
  for_ar?: string;
}
export interface SamplingDepthResponse {
  purpose?: string;
  depth_ar?: string;
  applies_to_ar?: string;
  principle_ar?: string;
  all_purposes_ar?: DepthPurposeRow[];
  disabled?: boolean;
}

/** soil_sampling_protocol.py — sampling_protocol(). */
export interface SamplingProtocolResponse {
  supported?: boolean;
  subsamples?: SamplingSubsamplesResponse;
  depth?: SamplingDepthResponse;
  steps_ar?: string[];
  avoid_ar?: string[];
  timing_ar?: string;
  yemen_note_ar?: string;
  disclaimer_ar?: string;
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

/** إدخال نسبة مئويّة (كما يفكّر المزارع) ⇒ كسر 0-1 (كما يتوقّع الخادم).
 *  تحويل وحدة بحت — لا حكم. فارغ/غير رقميّ ⇒ null. */
export function parsePctToFraction(text: string): number | null {
  const v = parseMeasure(text);
  return v == null ? null : v / 100;
}

// ── خرائط قيم معروفة (تلوين/تسمية عرضيّة فقط — المجهول محايد) ──────────────

/** مستويات confidence_engine.py: high/medium/low/very_low. الألوان عرضيّة؛
 *  المستوى المجهول يمرّ نصّه حرفيّاً بلون محايد (لا اختراع حكم). */
const CONFIDENCE_LEVELS: Record<string, { label_ar: string; color: string }> = {
  high: { label_ar: 'ثقة عالية', color: '#86efac' },
  medium: { label_ar: 'ثقة متوسّطة', color: '#7dd3fc' },
  low: { label_ar: 'ثقة منخفضة', color: '#fdba74' },
  very_low: { label_ar: 'ثقة شبه معدومة', color: '#fca5a5' },
};

export function confidenceBadge(level: string | null | undefined): { label_ar: string; color: string } {
  const known = level != null ? CONFIDENCE_LEVELS[level.toLowerCase()] : undefined;
  if (known) return known;
  return { label_ar: level ?? DASH, color: NEUTRAL };
}

/** قرارات soil_moisture_advisor.py: irrigate/monitor/safe — النصّ المعروض هو
 *  decision_ar من الخادم؛ هنا اللون فقط. مجهول ⇒ محايد. */
const MOISTURE_DECISION_COLORS: Record<string, string> = {
  irrigate: '#fca5a5',
  monitor: '#fdba74',
  safe: '#86efac',
};

export function moistureDecisionColor(decision: string | null | undefined): string {
  if (!decision) return NEUTRAL;
  return MOISTURE_DECISION_COLORS[decision.toLowerCase()] ?? NEUTRAL;
}

/** أسماء مدخلات التجميع (confidence_aggregation.py) — تسمية عرضيّة، المجهول يمرّ كما هو. */
const INPUT_NAMES_AR: Record<string, string> = {
  ndvi: 'NDVI',
  et0: 'ET₀',
  soil_moisture: 'رطوبة التربة',
  weather_forecast: 'توقّعات الطقس',
};

export function inputNameAr(key: string): string {
  return INPUT_NAMES_AR[key] ?? key;
}

/** أسماء المدخلات كما يعيدها الخادم ⇒ تسميات عرض؛ بلا مصفوفة ⇒ []. */
export function inputNamesAr(keys: string[] | null | undefined): string[] {
  if (!Array.isArray(keys)) return [];
  return keys.map(inputNameAr);
}

// ── خيارات إدخال ثابتة (مفاتيح API التي يعرفها الخادم — التسمية عرض فقط) ────

/** مفاتيح _SOIL_PARAMS في soil_moisture_advisor.py — القيَم المرجعيّة تُعرَض من
 *  /api/v1/irrigation/soil-types لا من هنا. */
export const SOIL_TYPE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'sand', label_ar: 'رمليّة' },
  { key: 'loam', label_ar: 'طميّة' },
  { key: 'clay', label_ar: 'طينيّة' },
];

/** مفاتيح METHOD_NAMES_AR في irrigation_method.py. */
export const IRRIGATION_METHOD_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'flood', label_ar: 'غمر' },
  { key: 'furrow', label_ar: 'أخاديد' },
  { key: 'sprinkler', label_ar: 'مرشّات' },
  { key: 'pivot', label_ar: 'محوري' },
  { key: 'drip', label_ar: 'تقطير' },
];

/** مفاتيح _DEPTH_GUIDE في soil_sampling_protocol.py. */
export const SAMPLING_PURPOSE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'general', label_ar: 'عامّ (أسمدة)' },
  { key: 'nitrate', label_ar: 'نترات' },
  { key: 'no_till', label_ar: 'بلا حراثة' },
  { key: 'orchard', label_ar: 'بساتين' },
];

// ── مشتقّات عرض من أشكال الخادم (الغائب يسقط، لا يُصفَّر) ──────────────────

/** رسالة الخادم لاستجابة غير مدعومة — تمرّ كما جاءت (supported=false ⇒ message_ar). */
export function unsupportedMessage(
  resp: { supported?: boolean; message_ar?: string } | null | undefined,
): string | null {
  if (!resp || resp.supported !== false) return null;
  return resp.message_ar ?? null;
}

/** مكوّنات ثقة NDVI (cloud/temporal/coverage/source) — كسور الخادم تُعرَض ٪. */
export function confidenceComponentFacts(resp: NdviConfidenceResponse | null | undefined): DisplayFact[] {
  const c = resp?.confidence?.components;
  if (!c) return [];
  const facts: DisplayFact[] = [];
  if (c.cloud != null) facts.push({ label: 'سحب', value: pctFromFraction(c.cloud) });
  if (c.temporal != null) facts.push({ label: 'حداثة', value: pctFromFraction(c.temporal) });
  if (c.coverage != null) facts.push({ label: 'تغطية', value: pctFromFraction(c.coverage) });
  if (c.source != null) facts.push({ label: 'مصدر', value: pctFromFraction(c.source) });
  return facts;
}

/** حقائق قرار الرطوبة من الشكل الحقيقيّ — ok=false ⇒ [] (error_ar يُعرَض مباشرةً). */
export function moistureFacts(resp: MoistureDecisionResponse | null | undefined): DisplayFact[] {
  if (!resp?.ok) return [];
  const facts: DisplayFact[] = [];
  if (resp.rwc_pct != null) facts.push({ label: 'المحتوى النسبي RWC', value: `${fmtNum(resp.rwc_pct, 1)}٪` });
  if (resp.vwc_pct != null) facts.push({ label: 'قراءة المستشعر VWC', value: `${fmtNum(resp.vwc_pct, 1)}٪` });
  if (resp.theta_fc != null) facts.push({ label: 'السعة الحقليّة θFC', value: fmtNum(resp.theta_fc, 3) });
  if (resp.theta_wp != null) facts.push({ label: 'نقطة الذبول θWP', value: fmtNum(resp.theta_wp, 3) });
  if (resp.soil_type_ar) facts.push({ label: 'التربة', value: resp.soil_type_ar });
  if (resp.calibrated != null) {
    // ترجمة عرضيّة لعلم الخادم calibrated — الحكم نفسه من الخادم لا منّا.
    facts.push({ label: 'المعايرة', value: resp.calibrated ? 'مُعايَرة ميدانيّاً' : 'قيم نوعيّة (غير معايَرة)' });
  }
  return facts;
}

/** حقائق الإجمالي المسحوب — أرقام الخادم كما هي (الكفاءة ٪ من كسر الخادم). */
export function grossFacts(resp: GrossIrrigationResponse | null | undefined): DisplayFact[] {
  if (!resp) return [];
  const facts: DisplayFact[] = [];
  if (resp.net_mm != null) facts.push({ label: 'الصافي', value: `${fmtNum(resp.net_mm, 1)} مم` });
  if (resp.gross_mm != null) facts.push({ label: 'الإجمالي المسحوب', value: `${fmtNum(resp.gross_mm, 1)} مم` });
  if (resp.gross_m3_ha != null) facts.push({ label: 'حجماً', value: `${fmtNum(resp.gross_m3_ha, 1)} م³/هكتار` });
  if (resp.application_efficiency != null) {
    facts.push({ label: 'كفاءة التطبيق', value: pctFromFraction(resp.application_efficiency) });
  }
  if (resp.pressurized != null) {
    facts.push({ label: 'الطاقة', value: resp.pressurized ? 'مضغوط (يحتاج ضخّاً)' : 'جاذبيّ' });
  }
  return facts;
}

export interface SoilTypeRow extends SoilTypeRef {
  key: string;
}

/** صفوف أنواع التربة من قاموس الخادم — بلا قاموس ⇒ [] بصدق. */
export function soilTypeRows(resp: SoilTypesResponse | null | undefined): SoilTypeRow[] {
  const dict = resp?.soil_types;
  if (!dict || typeof dict !== 'object') return [];
  return Object.entries(dict).map(([key, v]) => ({ key, ...v }));
}

/** محاصيل حساسيّة الماء كما يرتّبها الخادم — بلا مصفوفة ⇒ []. */
export function cropsRows(resp: WaterSensitivityCropsResponse | null | undefined): WaterSensitivityCrop[] {
  if (!resp || !Array.isArray(resp.crops)) return [];
  return resp.crops;
}

/** حقائق العيّنات الفرعيّة — supported=false ⇒ [] (message_ar عبر unsupportedMessage). */
export function subsampleFacts(resp: SamplingSubsamplesResponse | null | undefined): DisplayFact[] {
  if (!resp || resp.supported !== true) return [];
  const facts: DisplayFact[] = [];
  if (resp.subsamples != null) facts.push({ label: 'عيّنات فرعيّة', value: `~${fmtNum(resp.subsamples)}` });
  if (resp.area_ha != null) facts.push({ label: 'المساحة', value: `${fmtNum(resp.area_ha, 2)} هكتار` });
  return facts;
}

/** جدول الأعماق حسب الغرض كما يعيده الخادم — بلا مصفوفة ⇒ []. */
export function depthRows(resp: SamplingDepthResponse | null | undefined): DepthPurposeRow[] {
  if (!resp || !Array.isArray(resp.all_purposes_ar)) return [];
  return resp.all_purposes_ar;
}
