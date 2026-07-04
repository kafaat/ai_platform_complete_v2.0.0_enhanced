// Water Field Ops — يعكس نقاط backend اليتيمة (P1) التي كانت بلا قارئ واجهة:
//   /api/v1/water-sensitivity/stress-risk + /integrated-advice + /wheat-calendar
//                                               (crop_water_sensitivity.py — حساسيّة المراحل)
//   /api/v1/water-balance                       (water_balance.py — FAO-56 + قرار الملوحة)
//   /api/v1/water-harvesting/upstream-flood     (water_harvesting.py — مورد السيول الواردة)
//   /api/v1/lab/water-results                   (core/irrigation_water_analysis.py — SAR/RSC/EC)
//   /api/v1/weather/alerts + /api/v1/weather/layers (routers/weather.py — تنبيهات مشتقّة + manifest)
//   /api/v1/nutrients/4r-plan                   (nutrient_4r.py — خطّة 4R للتربة الكلسيّة)
//   /api/v1/outcome/record                      (routers/decision_record.py — إدامة النتيجة، كتابة)
//   /api/v1/geo-locate/field                    (geo_zone_locator.py — المحافظة/الإقليم من GPS)
//
// لا تكرار مع القائم: water-sensitivity/calendar وseasonal-risk في ClimateRiskCard،
// وwater-harvesting/{potential,methods,method-guide} في WaterHarvestingCard،
// وoutcome/measure (الحساب النقيّ بلا إدامة) في DecisionRuntimePage — هنا outcome/record
// (الإدامة في outcome_record + حدث OUTCOME_MEASURED) حصراً.
//
// صدق صارم: الأحكام والنصوص كلّها من الخادم وتمرّ حرفيّاً (advice_ar/…_ar) — لا يُعاد
// الحكم في الواجهة. null/غائب ⇒ «—» أو يسقط (لا تصفير ولا تلفيق). القياسات يُدخِلها
// المستخدم من قياس حقيقيّ (لا تخمين ⇒ لا استدعاء بلا مدخلات). خرائط القيم المعروفة هنا
// للتلوين/التسمية العرضيّة فقط، والمجهول ⇒ محايد مع تمرير نصّ الخادم كما جاء.

// ── أشكال الاستجابة الحقيقيّة كما يعيدها الخادم ─────────────────────────────

export interface DisplayFact {
  label: string;
  value: string;
}

/** api_models.py — StressRiskRequest (POST /api/v1/water-sensitivity/stress-risk). */
export interface StressRiskInput {
  crop: string;
  stage_key: string;
  depletion_pct: number;
}

/** api_models.py — IntegratedAdviceRequest (POST /api/v1/water-sensitivity/integrated-advice). */
export interface IntegratedAdviceInput extends StressRiskInput {
  net_irrigation_mm?: number | null;
}

/** crop_water_sensitivity.py — assess_stress_risk() (+حقول integrated_irrigation_advice). */
export interface StressRiskResponse {
  supported?: boolean;
  message_ar?: string;
  crop_ar?: string;
  stage_ar?: string;
  sensitivity?: string; // low|moderate|high|critical
  is_critical_window?: boolean;
  depletion_pct?: number;
  stress_level?: string; // ok|moderate|severe
  stress_level_ar?: string;
  urgent_irrigation?: boolean;
  advice_ar?: string;
  // — إضافات integrated_irrigation_advice عند تمرير net_irrigation_mm —
  net_irrigation_mm?: number;
  evidence_type?: string;
  corroboration_note_ar?: string;
  integrated_advice_ar?: string;
  /** 404 من الخادم ⇒ الميزة غير مُفعَّلة — حالة صادقة لا خطأ مُفزِع. */
  disabled?: boolean;
}

/** crop_water_sensitivity.py — wheat_water_calendar() (توافق خلفيّ + تحذير التشبّع). */
export interface WheatCalendarStage {
  stage_key?: string;
  name_ar?: string;
  sensitivity?: string;
  water_share_pct?: number;
  note_ar?: string;
  is_critical_window?: boolean;
}
export interface WheatCalendarResponse {
  supported?: boolean;
  message_ar?: string;
  crop?: string;
  crop_ar?: string;
  season_total_mm?: string;
  season_ar?: string;
  drought_tolerance_ar?: string;
  critical_window_ar?: string;
  irrigation_frequency_ar?: string;
  yemen_context_ar?: string;
  moderate_stress_threshold_ar?: string;
  stages?: WheatCalendarStage[];
  warning_waterlogging_ar?: string;
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** api/water_balance_models.py — WaterBalanceRequest (POST /api/v1/water-balance). */
export interface WaterBalanceInput {
  crop: string;
  stage?: string; // initial|development|mid|late
  t_min_c: number;
  t_max_c: number;
  rain_mm?: number;
  ndvi?: number | null;
  latitude_deg?: number;
  elevation_m?: number;
  day_of_year?: number;
  // تحليل ملوحة اختياريّ — حضوره يُفعّل مسار salinity_policy تلقائيّاً في الخادم
  soil_ece?: number | null;
  water_ecw?: number | null;
  analysis_age_days?: number | null;
  analysis_confidence?: number | null;
}

/** core/salinity_policy.py — SalinityDecision.to_dict(). */
export interface SalinityDecision {
  enabled?: boolean;
  reason_ar?: string;
  warn?: boolean;
  signals?: string[];
}

/** api/water_balance.py — WaterBalanceResult.to_dict() (+salinity_decision عند تمرير تحليل). */
export interface WaterBalanceResponse {
  et0_mm?: number;
  method?: string; // penman_monteith|hargreaves
  kc?: number;
  kc_source_ar?: string;
  etc_mm?: number;
  effective_rain_mm?: number;
  net_irrigation_mm?: number;
  advice_ar?: string;
  salinity_applied?: boolean;
  salinity_decision?: SalinityDecision;
  disabled?: boolean;
}

/** api/water_harvesting.py — upstream_flood_water() (نصوص مفاهيميّة كلّها من الخادم). */
export interface UpstreamFloodResponse {
  local_rain_mm?: number;
  concept_ar?: string;
  hazm_example_ar?: string;
  implication_ar?: string;
  caution_ar?: string;
  links_ar?: string;
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** core/irrigation_water_analysis.py — WaterSample (جسم POST /api/v1/lab/water-results).
 *  الأيونات بـmeq/L، EC بـdS/m — كلّها اختياريّة عدا sample_id (الخادم يُعلن الناقص). */
export interface WaterSamplePayload {
  sample_id: string;
  source?: string; // well | canal | mixed
  na?: number | null;
  ca?: number | null;
  mg?: number | null;
  hco3?: number | null;
  co3?: number | null;
  cl?: number | null;
  ec_dsm?: number | null;
  ph?: number | null;
  sampled_at?: string | null;
}

/** core/irrigation_water_analysis.py — analyze_water_sample(). */
export interface WaterClassification {
  class?: string | null;
  restriction_ar?: string;
  hazard_ar?: string;
  note_ar?: string;
}
export interface WaterLabAnalysis {
  sample_id?: string;
  source?: string;
  indices?: { sar?: number | null; rsc_meq_l?: number | null; ec_dsm?: number | null; ph?: number | null };
  classification?: {
    salinity?: WaterClassification;
    alkalinity_rsc?: WaterClassification;
    sodicity_sar?: WaterClassification;
  };
  hazard_flags_ar?: string[];
  suitable_ar?: string;
  missing_inputs?: string[];
  data_complete?: boolean;
}

/** routers/weather.py — GET /api/v1/weather/alerts (derive_weather_alerts — نقيّ). */
export interface WeatherAlert {
  type?: string;
  severity?: string; // info | warning | critical
  title_ar?: string;
  detail_ar?: string;
  window?: string;
}
export interface WeatherAlertsResponse {
  location?: { lat?: number; lon?: number };
  alerts?: WeatherAlert[];
  source?: string;
  disabled?: boolean;
}

/** routers/weather.py — GET /api/v1/weather/layers (manifest طبقات يرسمها SAHOOL). */
export interface WeatherLayerDef {
  key?: string;
  label_ar?: string;
  unit?: string;
  kind?: string; // weather | agro_weather | soil | risk | operation
  derived?: boolean;
  provider_native?: boolean;
  crop?: string;
  pathogen?: string;
  depth?: string;
}
export interface WeatherLayersResponse {
  source?: string;
  rendered_by?: string;
  times?: string[];
  models?: { key?: string; label_ar?: string }[];
  layers?: WeatherLayerDef[];
  operation_layers?: { key?: string; operation?: string; label_ar?: string }[];
  presets?: { key?: string; label_ar?: string; layer?: string }[];
  disabled?: boolean;
}

/** api_models.py — Soil4RRequest (POST /api/v1/nutrients/4r-plan) — قيم من تحليل مخبريّ. */
export interface Soil4RInput {
  caco3_pct?: number | null;
  ph?: number | null;
  p_ppm?: number | null;
  fe_ppm?: number | null;
  zn_ppm?: number | null;
  om_pct?: number | null;
  nutrients?: string[] | null;
}

/** nutrient_4r.py — FourRRecommendation.to_dict() (داخل {plan: [...]}) . */
export interface FourRPlanItem {
  nutrient?: string; // nitrogen|phosphorus|potassium|iron|zinc
  status?: string; // ok|blocked|advisory
  source_ar?: string;
  rate_ar?: string;
  timing_ar?: string;
  placement_ar?: string;
  warnings_ar?: string[];
}
export interface FourRPlanResponse {
  plan?: FourRPlanItem[];
  disabled?: boolean;
}

/** routers/decision_record.py — OutcomeRecordRequest (POST /api/v1/outcome/record).
 *  يختلف عن outcome/measure: هذا **يُدِيم** القياس في outcome_record (كتابة، يتطلّب Postgres). */
export interface OutcomeRecordInput {
  decision_id?: string | null;
  field_id?: string | null;
  region?: string | null;
  planned: {
    recommended_irrigation_mm?: number | null;
    predicted_stress_days?: number | null;
    expected_yield_t_ha?: number | null;
    season_budget_mm?: number | null;
  };
  actual: {
    actual_irrigation_mm?: number | null;
    observed_stress_days?: number | null;
    actual_yield_t_ha?: number | null;
    actual_water_used_mm?: number | null;
  };
  idempotency_key?: string | null;
}

export interface OutcomeMetricRow {
  key?: string;
  status?: string; // followed|under|over|better|worse|met|above|below|as_predicted|needs_data
  label_ar?: string;
  planned?: number | null;
  actual?: number | null;
  delta?: number | null;
}

/** routers/decision_record.py — ردّ record_outcome (persisted/replayed أعلام الخادم الصادقة). */
export interface OutcomeRecordResponse {
  outcome_id?: string;
  decision_id?: string;
  lineage?: Record<string, unknown>;
  metrics?: { metrics?: OutcomeMetricRow[]; warnings_ar?: string[]; data_completeness?: number };
  success?: boolean | null;
  persisted?: boolean;
  replayed?: boolean;
  recorded_by?: string;
}

/** api/geo_zone_locator.py — locate_field() (GET /api/v1/geo-locate/field). */
export interface GeoLocateFieldResponse {
  supported?: boolean;
  message_ar?: string;
  coordinates?: { lat?: number; lon?: number };
  elevation_m?: number | null;
  governorate_ar?: string;
  zone_source_ar?: string;
  zone?: string;
  zone_name_ar?: string;
  climate_ar?: string;
  temp_range_c?: number[];
  annual_rain_mm?: number[];
  humidity_pct?: number[];
  water_source_ar?: string;
  suited_crops_ar?: string[] | string;
  avoid_ar?: string[] | string;
  yemen_note_ar?: string;
  multi_zone_warning_ar?: string;
  disclaimer_ar?: string;
  source_ar?: string;
  disabled?: boolean;
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

/** يحلّل نصّ إدخال المستخدم إلى رقم — فارغ/غير رقميّ ⇒ null (لا افتراض). */
export function parseMeasure(text: string): number | null {
  const t = text.trim();
  if (t === '') return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

/** مدى الخادم [أدنى، أعلى] ⇒ نصّ عرض؛ غائب/ناقص ⇒ «—». */
export function fmtRange(range: number[] | null | undefined, unit = ''): string {
  if (!Array.isArray(range) || range.length < 2 || range[0] == null || range[1] == null) return DASH;
  return `${range[0]}–${range[1]}${unit}`;
}

/** قوائم الخادم قد تأتي نصّاً واحداً أو مصفوفة — توحيد عرضيّ بلا تلفيق. */
export function listOrText(v: string[] | string | null | undefined): string | null {
  if (v == null) return null;
  if (Array.isArray(v)) return v.length > 0 ? v.join('، ') : null;
  return v || null;
}

/** رسالة الخادم لاستجابة غير مدعومة — تمرّ كما جاءت (supported=false ⇒ message_ar). */
export function unsupportedMessage(
  resp: { supported?: boolean; message_ar?: string } | null | undefined,
): string | null {
  if (!resp || resp.supported !== false) return null;
  return resp.message_ar ?? null;
}

// ── خيارات إدخال ثابتة (مفاتيح API التي يعرفها الخادم — التسمية عرض فقط) ────

/** مفاتيح _CROPS في crop_water_sensitivity.py — الأسماء عرض تطابق name_ar الخادم. */
export const WATER_CROP_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'wheat', label_ar: 'القمح' },
  { key: 'maize', label_ar: 'الذرة الشاميّة' },
  { key: 'sorghum', label_ar: 'الذرة الرفيعة' },
  { key: 'millet', label_ar: 'الدخن' },
  { key: 'barley', label_ar: 'الشعير' },
];

/** مفاتيح مراحل كلّ محصول كما في سجلّ الخادم _CROPS — عقد API لا اجتهاد واجهة. */
export const STAGE_OPTIONS_BY_CROP: Record<string, { key: string; label_ar: string }[]> = {
  wheat: [
    { key: 'germination', label_ar: 'الإنبات' },
    { key: 'tillering', label_ar: 'الإشطاء' },
    { key: 'stem_elongation', label_ar: 'الاستطالة' },
    { key: 'flowering', label_ar: 'الإزهار' },
    { key: 'grain_filling', label_ar: 'تكوين الحبوب' },
    { key: 'maturity', label_ar: 'النضج' },
  ],
  maize: [
    { key: 'emergence', label_ar: 'الإنبات والظهور' },
    { key: 'vegetative', label_ar: 'النمو الخضري' },
    { key: 'tasseling', label_ar: 'التزهير والتلقيح' },
    { key: 'grain_filling', label_ar: 'امتلاء الحبوب' },
    { key: 'maturity', label_ar: 'النضج' },
  ],
  sorghum: [
    { key: 'emergence', label_ar: 'الإنبات' },
    { key: 'vegetative', label_ar: 'النمو الخضري' },
    { key: 'booting_flowering', label_ar: 'طرد السنابل والإزهار' },
    { key: 'grain_filling', label_ar: 'امتلاء الحبوب' },
    { key: 'maturity', label_ar: 'النضج' },
  ],
  millet: [
    { key: 'emergence', label_ar: 'الإنبات' },
    { key: 'vegetative', label_ar: 'النمو الخضري' },
    { key: 'flowering', label_ar: 'الإزهار' },
    { key: 'grain_filling', label_ar: 'امتلاء الحبوب' },
    { key: 'maturity', label_ar: 'النضج' },
  ],
  barley: [
    { key: 'germination', label_ar: 'الإنبات' },
    { key: 'tillering', label_ar: 'الإشطاء' },
    { key: 'stem_elongation', label_ar: 'الاستطالة' },
    { key: 'flowering', label_ar: 'الإزهار' },
    { key: 'grain_filling', label_ar: 'امتلاء الحبوب' },
    { key: 'maturity', label_ar: 'النضج' },
  ],
};

/** مراحل المحصول المختار — محصول مجهول ⇒ [] (الخادم سيعلن unsupported بنفسه). */
export function stagesForCrop(crop: string | null | undefined): { key: string; label_ar: string }[] {
  if (!crop) return [];
  return STAGE_OPTIONS_BY_CROP[crop] ?? [];
}

/** مراحل FAO-56 في WaterBalanceRequest (stage افتراضيّ الخادم mid). */
export const WB_STAGE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'initial', label_ar: 'أوّليّة' },
  { key: 'development', label_ar: 'تطوّر' },
  { key: 'mid', label_ar: 'وسطى' },
  { key: 'late', label_ar: 'متأخّرة' },
];

/** مصادر WaterSample في core/irrigation_water_analysis.py (افتراضيّ الخادم well). */
export const WATER_SOURCE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'well', label_ar: 'بئر' },
  { key: 'canal', label_ar: 'قناة/ساقية' },
  { key: 'mixed', label_ar: 'مختلط' },
];

// ── خرائط قيم معروفة (تلوين/تسمية عرضيّة فقط — المجهول محايد) ──────────────

/** مستويات stress_level من assess_stress_risk: ok/moderate/severe — النصّ المعروض
 *  هو stress_level_ar من الخادم؛ هنا اللون فقط. مجهول ⇒ محايد. */
const STRESS_LEVEL_COLORS: Record<string, string> = {
  ok: '#86efac',
  moderate: '#fdba74',
  severe: '#fca5a5',
};
export function stressLevelColor(level: string | null | undefined): string {
  if (!level) return NEUTRAL;
  return STRESS_LEVEL_COLORS[level.toLowerCase()] ?? NEUTRAL;
}

/** حساسيّة المراحل (WaterSensitivity في الخادم): low/moderate/high/critical. */
const SENSITIVITY_COLORS: Record<string, string> = {
  low: '#86efac',
  moderate: '#fde68a',
  high: '#fdba74',
  critical: '#fca5a5',
};
export function sensitivityColor(s: string | null | undefined): string {
  if (!s) return NEUTRAL;
  return SENSITIVITY_COLORS[s.toLowerCase()] ?? NEUTRAL;
}

/** شدّات تنبيهات الطقس (derive_weather_alerts): info/warning/critical. */
const ALERT_SEVERITY_COLORS: Record<string, string> = {
  info: '#7dd3fc',
  warning: '#fdba74',
  critical: '#fca5a5',
};
export function alertSeverityColor(sev: string | null | undefined): string {
  if (!sev) return NEUTRAL;
  return ALERT_SEVERITY_COLORS[sev.toLowerCase()] ?? NEUTRAL;
}

/** حالات RecommendationStatus في nutrient_4r.py: ok/blocked/advisory. */
const NUTRIENT_STATUS: Record<string, { label_ar: string; color: string }> = {
  ok: { label_ar: 'توصية جاهزة', color: '#86efac' },
  advisory: { label_ar: 'إرشاد عامّ (بلا معدّل دقيق)', color: '#fde68a' },
  blocked: { label_ar: 'محجوبة — تحتاج تحليل مختبر', color: '#fca5a5' },
};
export function nutrientStatusBadge(status: string | null | undefined): { label_ar: string; color: string } {
  const known = status != null ? NUTRIENT_STATUS[status.toLowerCase()] : undefined;
  if (known) return known;
  return { label_ar: status ?? DASH, color: NEUTRAL };
}

/** أسماء العناصر (Nutrient enum) — تسمية عرضيّة، المجهول يمرّ كما هو. */
const NUTRIENT_NAMES_AR: Record<string, string> = {
  nitrogen: 'النيتروجين N',
  phosphorus: 'الفوسفور P',
  potassium: 'البوتاسيوم K',
  iron: 'الحديد Fe',
  zinc: 'الزنك Zn',
};
export function nutrientNameAr(key: string | null | undefined): string {
  if (!key) return DASH;
  return NUTRIENT_NAMES_AR[key.toLowerCase()] ?? key;
}

/** خلاصة نجاح outcome/record الصادقة: null من الخادم = «لا مقياس مُقيَّم» لا فشل. */
export function outcomeSuccessLabel(success: boolean | null | undefined): { label_ar: string; color: string } {
  if (success === true) return { label_ar: 'ضمن هدف القرار', color: '#86efac' };
  if (success === false) return { label_ar: 'انحراف عن هدف القرار', color: '#fca5a5' };
  return { label_ar: 'بلا حكم (لا مقياس مُقيَّم)', color: NEUTRAL };
}

// ── بناة مدخلات (فارغ ⇒ null: لا استدعاء بلا قياس حقيقيّ) ───────────────────

/** مدخل خطر الإجهاد — يلزم محصول + مرحلة + نضوب (٪ من قياس/تقدير المستخدم). */
export function buildStressInput(
  crop: string,
  stageKey: string,
  depletionText: string,
): StressRiskInput | null {
  const depletion = parseMeasure(depletionText);
  if (!crop || !stageKey || depletion == null) return null;
  return { crop, stage_key: stageKey, depletion_pct: depletion };
}

/** مدخل النصيحة المتكاملة — نفس خطر الإجهاد + صافي الريّ (مم، من ميزان الماء). */
export function buildIntegratedInput(
  crop: string,
  stageKey: string,
  depletionText: string,
  netMmText: string,
): IntegratedAdviceInput | null {
  const base = buildStressInput(crop, stageKey, depletionText);
  const net = parseMeasure(netMmText);
  // النصيحة المتكاملة تتمايز عن خطر الإجهاد بوجود صافي الريّ — غيابه ⇒ لا استدعاء.
  if (!base || net == null) return null;
  return { ...base, net_irrigation_mm: net };
}

export interface WaterBalanceFormText {
  crop: string;
  stage: string;
  tMin: string;
  tMax: string;
  rainMm: string;
  latitude: string;
  elevation: string;
  dayOfYear: string;
  soilEce: string;
  waterEcw: string;
  analysisAgeDays: string;
  analysisConfidencePct: string;
}

/** مدخل ميزان الماء — الإلزاميّ: محصول + حرارتان (من قياس). الاختياريّ يُرسَل فقط
 *  إن أدخله المستخدم (غيابه يُبقي افتراضات الخادم المعلَنة في عقده — لا نكرّرها هنا).
 *  حقول الملوحة تُرسَل فقط عند إدخالها — حضور أيّ منها يُفعّل مسار salinity_policy. */
export function buildWaterBalanceInput(f: WaterBalanceFormText): WaterBalanceInput | null {
  const tMin = parseMeasure(f.tMin);
  const tMax = parseMeasure(f.tMax);
  if (!f.crop.trim() || tMin == null || tMax == null) return null;
  const input: WaterBalanceInput = { crop: f.crop.trim(), t_min_c: tMin, t_max_c: tMax };
  if (f.stage) input.stage = f.stage;
  const rain = parseMeasure(f.rainMm);
  if (rain != null) input.rain_mm = rain;
  const lat = parseMeasure(f.latitude);
  if (lat != null) input.latitude_deg = lat;
  const elev = parseMeasure(f.elevation);
  if (elev != null) input.elevation_m = elev;
  const doy = parseMeasure(f.dayOfYear);
  if (doy != null) input.day_of_year = doy;
  const ece = parseMeasure(f.soilEce);
  if (ece != null) input.soil_ece = ece;
  const ecw = parseMeasure(f.waterEcw);
  if (ecw != null) input.water_ecw = ecw;
  const age = parseMeasure(f.analysisAgeDays);
  if (age != null) input.analysis_age_days = age;
  const confPct = parseMeasure(f.analysisConfidencePct);
  // الثقة تُدخَل ٪ (كما يفكّر المستخدم) وتُرسَل كسراً 0-1 (كما يتوقّع الخادم) — تحويل وحدة بحت.
  if (confPct != null) input.analysis_confidence = confPct / 100;
  return input;
}

/** حقائق ميزان الماء من الشكل الحقيقيّ — الغائب يسقط لا يُصفَّر. */
export function waterBalanceFacts(resp: WaterBalanceResponse | null | undefined): DisplayFact[] {
  if (!resp) return [];
  const facts: DisplayFact[] = [];
  if (resp.et0_mm != null) facts.push({ label: 'ET₀', value: `${fmtNum(resp.et0_mm, 2)} مم/يوم` });
  if (resp.kc != null) facts.push({ label: 'Kc', value: fmtNum(resp.kc, 2) });
  if (resp.etc_mm != null) facts.push({ label: 'ETc', value: `${fmtNum(resp.etc_mm, 2)} مم/يوم` });
  if (resp.effective_rain_mm != null) {
    facts.push({ label: 'المطر الفعّال', value: `${fmtNum(resp.effective_rain_mm, 1)} مم` });
  }
  if (resp.net_irrigation_mm != null) {
    facts.push({ label: 'الصافي المطلوب', value: `${fmtNum(resp.net_irrigation_mm, 1)} مم` });
  }
  return facts;
}

/** فقرات مورد السيول كما أرسلها الخادم بترتيبها — الغائب يسقط. caution_ar يُعرَض
 *  منفصلاً (تحذير) في البطاقة، لذا لا يدخل هنا. */
export function floodParagraphs(resp: UpstreamFloodResponse | null | undefined): string[] {
  if (!resp) return [];
  return [resp.concept_ar, resp.hazm_example_ar, resp.implication_ar, resp.links_ar]
    .filter((s): s is string => typeof s === 'string' && s.length > 0);
}

export interface WaterSampleFormText {
  sampleId: string;
  source: string;
  na: string;
  ca: string;
  mg: string;
  hco3: string;
  co3: string;
  cl: string;
  ecDsm: string;
  ph: string;
  sampledAt: string;
}

/** جسم عيّنة الماء — sample_id إلزاميّ؛ كلّ قياس اختياريّ يُرسَل فقط إن أُدخل
 *  (الخادم يُعلن missing_inputs بصدق — لا نُصفّر الغائب). */
export function buildWaterSamplePayload(f: WaterSampleFormText): WaterSamplePayload | null {
  const sampleId = f.sampleId.trim();
  if (!sampleId) return null;
  const payload: WaterSamplePayload = { sample_id: sampleId };
  if (f.source) payload.source = f.source;
  type NumKey = 'na' | 'ca' | 'mg' | 'hco3' | 'co3' | 'cl' | 'ec_dsm' | 'ph';
  const nums: [NumKey, string][] = [
    ['na', f.na], ['ca', f.ca], ['mg', f.mg], ['hco3', f.hco3],
    ['co3', f.co3], ['cl', f.cl], ['ec_dsm', f.ecDsm], ['ph', f.ph],
  ];
  for (const [key, text] of nums) {
    const v = parseMeasure(text);
    if (v != null) payload[key] = v;
  }
  if (f.sampledAt) payload.sampled_at = f.sampledAt;
  return payload;
}

/** مؤشّرات تحليل الماء (SAR/RSC/EC/pH) — أرقام الخادم كما هي، الغائب يسقط. */
export function waterIndicesFacts(a: WaterLabAnalysis | null | undefined): DisplayFact[] {
  const idx = a?.indices;
  if (!idx) return [];
  const facts: DisplayFact[] = [];
  if (idx.sar != null) facts.push({ label: 'SAR', value: fmtNum(idx.sar, 2) });
  if (idx.rsc_meq_l != null) facts.push({ label: 'RSC', value: `${fmtNum(idx.rsc_meq_l, 2)} meq/L` });
  if (idx.ec_dsm != null) facts.push({ label: 'EC', value: `${fmtNum(idx.ec_dsm, 2)} dS/m` });
  if (idx.ph != null) facts.push({ label: 'pH', value: fmtNum(idx.ph, 1) });
  return facts;
}

export interface ClassificationRow {
  label_ar: string;
  /** نصّ الخادم كما جاء: restriction_ar أو hazard_ar أو note_ar («غير مقيس/غير محسوب»). */
  text_ar: string;
}

/** صفوف تصنيف الماء — نصوص الخادم حرفيّاً (بما فيها إعلان «غير محسوب» الصادق). */
export function classificationRows(a: WaterLabAnalysis | null | undefined): ClassificationRow[] {
  const c = a?.classification;
  if (!c) return [];
  const rows: ClassificationRow[] = [];
  const pick = (label: string, w: WaterClassification | undefined) => {
    if (!w) return;
    const text = w.restriction_ar ?? w.hazard_ar ?? w.note_ar;
    if (text) rows.push({ label_ar: label, text_ar: text });
  };
  pick('الملوحة (EC)', c.salinity);
  pick('القلويّة (RSC)', c.alkalinity_rsc);
  pick('الصوديوم (SAR)', c.sodicity_sar);
  return rows;
}

/** تنبيهات الطقس كما رتّبها الخادم — بلا مصفوفة ⇒ []. */
export function alertRows(resp: WeatherAlertsResponse | null | undefined): WeatherAlert[] {
  if (!resp || !Array.isArray(resp.alerts)) return [];
  return resp.alerts;
}

/** طبقات manifest الطقس — بلا مصفوفة ⇒ []. */
export function layerRows(resp: WeatherLayersResponse | null | undefined): WeatherLayerDef[] {
  if (!resp || !Array.isArray(resp.layers)) return [];
  return resp.layers;
}

/** تسمية طبقة للعرض: label_ar + الوحدة + وسم «مشتقّة» لعلم الخادم derived. */
export function layerCaption(l: WeatherLayerDef): string {
  const parts: string[] = [l.label_ar ?? l.key ?? DASH];
  if (l.unit) parts.push(`(${l.unit})`);
  if (l.derived === true) parts.push('· مشتقّة');
  return parts.join(' ');
}

export interface Soil4RFormText {
  caco3Pct: string;
  ph: string;
  pPpm: string;
  fePpm: string;
  znPpm: string;
  omPct: string;
}

/** مدخل خطّة 4R — يلزم قياس مخبريّ واحد على الأقلّ (لا خطّة من لا شيء؛ الخادم
 *  نفسه يحجب ما يحتاج تحليلاً). قائمة العناصر تُترك للخادم (افتراضيّه N/P/Fe/Zn). */
export function build4rInput(f: Soil4RFormText): Soil4RInput | null {
  const input: Soil4RInput = {};
  const map: [keyof Soil4RInput, string][] = [
    ['caco3_pct', f.caco3Pct], ['ph', f.ph], ['p_ppm', f.pPpm],
    ['fe_ppm', f.fePpm], ['zn_ppm', f.znPpm], ['om_pct', f.omPct],
  ];
  let any = false;
  for (const [key, text] of map) {
    const v = parseMeasure(text);
    if (v != null) {
      (input as Record<string, unknown>)[key] = v;
      any = true;
    }
  }
  return any ? input : null;
}

/** بنود الخطّة كما رتّبها الخادم — بلا مصفوفة ⇒ []. */
export function planRows(resp: FourRPlanResponse | null | undefined): FourRPlanItem[] {
  if (!resp || !Array.isArray(resp.plan)) return [];
  return resp.plan;
}

export interface OutcomeRecordFormText {
  decisionId: string;
  recommendedIrrigationMm: string;
  predictedStressDays: string;
  expectedYieldTHa: string;
  seasonBudgetMm: string;
  actualIrrigationMm: string;
  observedStressDays: string;
  actualYieldTHa: string;
  actualWaterUsedMm: string;
  idempotencyKey: string;
}

/** مدخل إدامة النتيجة — قيمة واحدة على الأقلّ (مُخطَّطة أو مرصودة) وإلّا null:
 *  لا نُدِيم سجلّاً فارغاً. الفارغ يبقى غائباً (الخادم يقول needs_data بصدق). */
export function buildOutcomeRecordInput(
  f: OutcomeRecordFormText,
  fieldId: string | null | undefined,
): OutcomeRecordInput | null {
  const planned: OutcomeRecordInput['planned'] = {};
  const actual: OutcomeRecordInput['actual'] = {};
  let any = false;
  const put = (obj: Record<string, unknown>, key: string, text: string) => {
    const v = parseMeasure(text);
    if (v != null) {
      obj[key] = v;
      any = true;
    }
  };
  put(planned, 'recommended_irrigation_mm', f.recommendedIrrigationMm);
  put(planned, 'predicted_stress_days', f.predictedStressDays);
  put(planned, 'expected_yield_t_ha', f.expectedYieldTHa);
  put(planned, 'season_budget_mm', f.seasonBudgetMm);
  put(actual, 'actual_irrigation_mm', f.actualIrrigationMm);
  put(actual, 'observed_stress_days', f.observedStressDays);
  put(actual, 'actual_yield_t_ha', f.actualYieldTHa);
  put(actual, 'actual_water_used_mm', f.actualWaterUsedMm);
  if (!any) return null;
  const input: OutcomeRecordInput = { planned, actual };
  const decisionId = f.decisionId.trim();
  if (decisionId) input.decision_id = decisionId;
  if (fieldId) input.field_id = fieldId;
  const idem = f.idempotencyKey.trim();
  if (idem) input.idempotency_key = idem;
  return input;
}

/** مقاييس ردّ outcome/record — الشكل المتداخل metrics.metrics؛ بلا مصفوفة ⇒ []. */
export function outcomeMetricRows(resp: OutcomeRecordResponse | null | undefined): OutcomeMetricRow[] {
  const rows = resp?.metrics?.metrics;
  if (!Array.isArray(rows)) return [];
  return rows;
}

/** حقائق تحديد الموقع الجغرافيّ — الغائب يسقط؛ المدى يُعرَض كما أرسله الخادم. */
export function geoFacts(resp: GeoLocateFieldResponse | null | undefined): DisplayFact[] {
  if (!resp?.supported) return [];
  const facts: DisplayFact[] = [];
  if (resp.governorate_ar) facts.push({ label: 'المحافظة', value: resp.governorate_ar });
  if (resp.zone_name_ar) facts.push({ label: 'الإقليم', value: resp.zone_name_ar });
  if (resp.temp_range_c) facts.push({ label: 'الحرارة', value: fmtRange(resp.temp_range_c, '°م') });
  if (resp.annual_rain_mm) facts.push({ label: 'المطر السنويّ', value: fmtRange(resp.annual_rain_mm, ' مم') });
  if (resp.humidity_pct) facts.push({ label: 'الرطوبة', value: fmtRange(resp.humidity_pct, '٪') });
  return facts;
}

/** خطأ HTTP ⇒ رمز الحالة إن وُجد (لتمييز 404 «غير مُفعَّل» و503 «قاعدة غير متاحة»
 *  في مسارات الكتابة عبر useMutation — الاستعلامات تعالجها hooks بنمط disabled). */
export function httpStatusOf(e: unknown): number | null {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return typeof status === 'number' ? status : null;
}

/** نصّ خطأ كتابة صادق: 404 غير مُفعَّل، 403 صلاحيّة، 503 قاعدة/إثبات ملكيّة،
 *  ويُفضَّل detail العربيّ من الخادم إن وُجد. */
export function writeErrorMessage(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail.length > 0) return detail;
  const status = httpStatusOf(e);
  if (status === 404) return 'هذه الميزة غير مُفعَّلة على هذا الخادم.';
  if (status === 403) return 'غير مصرَّح: تحتاج صلاحيّة أعلى لهذا الإجراء.';
  if (status === 503) return 'قاعدة البيانات غير متاحة الآن — لم يُسجَّل شيء. أعد المحاولة لاحقاً.';
  return 'تعذّر الإرسال إلى الخادم — لم يُسجَّل شيء.';
}
