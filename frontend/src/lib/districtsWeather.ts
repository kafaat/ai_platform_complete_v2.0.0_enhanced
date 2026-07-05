// districtsWeather — مساعِدات نقيّة لنقاط backend اليتيمة (P2):
//   • طبقة المعرفة الإقليميّة   /api/v1/districts · /districts/{id} · /districts/{id}/active-pests
//   • توصية الموقع الجغرافيّ    /api/v1/geo-locate/recommend
//   • ملخّص طقس الحقل + تحليلات /api/v1/weather/field-weather-summary ·
//                               /api/v1/weather-analytics/analyze · /planting-guide
//   • استبيان التهيئة            /api/v1/onboarding/questionnaire (GET) · /responses (POST)
//
// صدق صارم (سابقة waterHarvesting.ts): كلّ النصوص والأحكام من الخادم تمرّ حرفيّاً
// (note_ar/advice_ar/disclaimer_ar/message_ar وقوائم الآفات/التوصيات لا يُعاد الحكم
// عليها هنا)؛ null ⇒ «—»؛ الغائب يسقط لا يُصفَّر؛ والقياسات (إحداثيّات/سجلّ طقس/إجابات)
// يُدخِلها المستخدم من مصدر حقيقيّ لا تُخمَّن. 404 ⇒ {disabled:true} من الهوك.

// ── أشكال الاستجابة الحقيقيّة ──────────────────────────────────────────────
// المصادر:
//   services/sahool-platform/api/routers/districts.py + core/districts/loader.py
//   services/sahool-platform/api/geo_zone_locator.py (locate_and_recommend)
//   services/sahool-platform/api/routers/weather.py (weather_field_summary)
//   services/sahool-platform/api/weather_analytics.py
//   services/sahool-platform/api/onboarding.py

/** لاحقة موحّدة لكلّ استجابة قد يُرجِع عنها الهوك حالة «غير مُفعَّل» عند 404. */
export interface MaybeDisabled {
  disabled?: boolean;
}

export interface DistrictSummary {
  district_id: string;
  name_ar?: string | null;
  agro_ecological_zone_ar?: string | null;
  altitude_range_m?: [number, number] | number[] | null;
}

export interface DistrictsIndexResponse extends MaybeDisabled {
  total_districts?: number;
  districts?: DistrictSummary[];
  note_ar?: string;
}

/** نافذة خطر إقليميّة — قرينة معرفيّة مُسنَدة بمصدر (loader.REQUIRED_WINDOW). */
export interface PestWindow {
  pest: string;
  pest_ar: string;
  crops: string[];
  risk_months: number[];
  severity: string; // low | medium | high (عقد الخادم؛ نعرض الغريب محايداً)
  scouting_cue_ar: string;
  source: string;
}

export interface DistrictCard extends MaybeDisabled {
  district_id?: string;
  name_ar?: string | null;
  agro_ecological_zone_ar?: string | null;
  altitude_range_m?: [number, number] | number[] | null;
  pest_windows?: PestWindow[];
}

export interface ActivePestsResponse extends MaybeDisabled {
  district_id?: string;
  month?: number;
  active_pest_count?: number;
  active_pests?: PestWindow[];
}

/** توصية الموقع = مخرَج locate_field + recommendation_ar (locate_and_recommend). */
export interface GeoRecommendResponse extends MaybeDisabled {
  supported?: boolean;
  message_ar?: string;
  coordinates?: { lat: number; lon: number };
  elevation_m?: number | null;
  governorate_ar?: string;
  zone_source_ar?: string;
  zone?: string;
  zone_name_ar?: string;
  climate_ar?: string;
  temp_range_c?: number[] | null;
  annual_rain_mm?: number[] | null;
  humidity_pct?: number[] | null;
  water_source_ar?: string;
  suited_crops_ar?: string[] | null;
  avoid_ar?: string[] | null;
  yemen_note_ar?: string;
  multi_zone_warning_ar?: string;
  disclaimer_ar?: string;
  source_ar?: string;
  recommendation_ar?: {
    suited_crops_ar?: string[] | null;
    avoid_ar?: string[] | null;
    rainfed_possible?: boolean;
    water_note_ar?: string;
    global_analogs_ar?: unknown;
    next_step_ar?: string;
  };
}

/** صلاحيّة عمليّة واحدة (_operation_suitability). */
export interface OperationSuitability {
  operation: string;
  score: number; // 0..1
  suitability: string; // optimal | acceptable | poor | unsafe
  limiting_factors: string[];
}

export interface FieldWeatherSummaryResponse extends MaybeDisabled {
  location?: { lat: number; lon: number };
  time?: string;
  model?: string;
  sample?: Record<string, unknown>;
  operations?: Record<string, OperationSuitability>;
  alerts_ar?: string[];
  cache_state?: string;
  cache_age_s?: number | null;
  upstream_error?: string | null;
  source?: string;
}

/** مخرَج analyze_weather_log — كلّ الحقول محسوبة في الخادم. */
export interface WeatherAnalysisResponse extends MaybeDisabled {
  supported?: boolean;
  message_ar?: string;
  days_analyzed?: number;
  heat_stress_days?: number;
  severe_heat_days?: number;
  frost_days?: number;
  high_wind_days?: number;
  total_rainfall_mm?: number;
  annual_rainfall_mm?: number;
  computed_et0_total_mm?: number;
  annual_et0_mm?: number;
  annual_water_deficit_mm?: number;
  irrigation_dependency_ar?: string;
  heat_window_ar?: string;
  verdict_ar?: string;
  note_ar?: string;
  disclaimer_ar?: string;
}

export interface PlantingGuideMonth {
  month: number;
  month_ar: string;
  avg_tmax_c: number;
  window: string; // optimal | transition | heat_stress
  window_ar: string;
}

export interface PlantingGuideResponse extends MaybeDisabled {
  supported?: boolean;
  message_ar?: string;
  months?: PlantingGuideMonth[];
  optimal_season_ar?: string[];
  heat_stress_season_ar?: string[];
  summary_ar?: string;
  disclaimer_ar?: string;
}

export interface OnboardingQuestionDef {
  id: string;
  label_ar: string;
  type: string; // text|number|select|multiselect|date|gps|polygon|photo|audio
  required?: boolean;
  unit?: string | null;
  options?: string[] | null;
  hint_ar?: string | null;
}

export interface OnboardingSectionDef {
  id: string;
  title_ar: string;
  phase: number; // 1 = إلزامي مبدئي · 2 = تعميق اختياري
  questions: OnboardingQuestionDef[];
}

export interface QuestionnaireResponse extends MaybeDisabled {
  version?: string;
  rtl?: boolean;
  lang?: string;
  offline_capable?: boolean;
  sections?: OnboardingSectionDef[];
  required_count?: number;
}

/** مخرَج submit_onboarding (POST /responses). */
export interface OnboardingSubmitResponse extends MaybeDisabled {
  id?: string | number | null;
  valid?: boolean;
  missing_required?: string[];
  answered_count?: number;
}

/** جسم POST /responses — يطابق OnboardingSubmitRequest (field_id?, answers). */
export interface OnboardingSubmitPayload {
  field_id: string | null;
  answers: Record<string, unknown>;
}

/** سجلّ طقس يوميّ لِـanalyze/planting-guide (analyze_weather_log). */
export interface WeatherRecord {
  date: string;
  temp_max_c: number;
  temp_min_c: number;
  precipitation_mm?: number;
  wind_speed_kmh?: number;
}

export interface DisplayFact {
  label: string;
  value: string;
}

const DASH = '—';

// ── مساعِدات عامّة ─────────────────────────────────────────────────────────

/** حالة «غير مُفعَّل» الصادقة (404 من الهوك) — نميّزها عن unsupported الدلاليّ. */
export function isDisabled(resp: MaybeDisabled | null | undefined): boolean {
  return resp?.disabled === true;
}

/** تنسيق رقم للعرض — null/undefined/غير منتهٍ ⇒ «—» (لا تصفير). */
export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return v.toFixed(digits);
}

/** رسالة الخادم لاستجابة غير مدعومة دلاليّاً (supported===false ⇒ message_ar). */
export function serverMessage(
  resp: { supported?: boolean; message_ar?: string } | null | undefined,
): string | null {
  if (!resp || resp.supported !== false) return null;
  return resp.message_ar ?? null;
}

/** مدى مجال [min,max] كنصّ — الغائب/غير الزوجيّ ⇒ «—» (لا تلفيق حدود). */
export function rangeText(range: number[] | null | undefined, unit = ''): string {
  if (!Array.isArray(range) || range.length < 2) return DASH;
  const [a, b] = range;
  if (!Number.isFinite(a) || !Number.isFinite(b)) return DASH;
  const suffix = unit ? ` ${unit}` : '';
  return `${a}–${b}${suffix}`;
}

// ── المديريّات (districts) ─────────────────────────────────────────────────

/** فهرس المديريّات كما رتّبه الخادم — بلا مصفوفة ⇒ [] بصدق. */
export function districtOptions(resp: DistrictsIndexResponse | null | undefined): DistrictSummary[] {
  if (!resp || !Array.isArray(resp.districts)) return [];
  return resp.districts.filter((d) => !!d && !!d.district_id);
}

/** تسمية عرض للمديريّة — الاسم ثمّ الإقليم الزراعيّ-البيئيّ إن توفّرا. */
export function districtLabel(d: DistrictSummary | null | undefined): string {
  if (!d) return DASH;
  return d.name_ar || d.district_id || DASH;
}

/** لون شدّة نافذة الخطر — العقد المعروف فقط؛ الغريب/الغائب محايد (سابقة riskColor). */
export function severityColor(sev: string | null | undefined): string {
  switch ((sev || '').toLowerCase()) {
    case 'high':
      return '#fca5a5';
    case 'medium':
      return '#fdba74';
    case 'low':
      return '#86efac';
    default:
      return '#64748b';
  }
}

/** تسمية عربيّة للشدّة — الغريب يُعرَض كما جاء (لا نُخفي المجهول). */
export function severityLabelAr(sev: string | null | undefined): string {
  switch ((sev || '').toLowerCase()) {
    case 'high':
      return 'عالية';
    case 'medium':
      return 'متوسّطة';
    case 'low':
      return 'منخفضة';
    default:
      return sev || DASH;
  }
}

const MONTHS_AR = [
  'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
  'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر',
];

/** اسم الشهر العربيّ — يحرس النطاق 1..12 (عقد الخادم) وإلّا «—». */
export function monthNameAr(m: number | null | undefined): string {
  if (m == null || !Number.isInteger(m) || m < 1 || m > 12) return DASH;
  return MONTHS_AR[m - 1];
}

/** خيارات الأشهر لِمُنتقي active-pests (1..12 بأسمائها). */
export function monthOptions(): { value: number; label_ar: string }[] {
  return MONTHS_AR.map((label_ar, i) => ({ value: i + 1, label_ar }));
}

/** نوافذ الخطر لبطاقة المديريّة — بلا مصفوفة ⇒ []. */
export function pestWindows(card: DistrictCard | null | undefined): PestWindow[] {
  if (!card || !Array.isArray(card.pest_windows)) return [];
  return card.pest_windows;
}

/** الآفات النشطة في الشهر المطلوب — قائمة فارغة صادقة إن لم تنطبق نافذة. */
export function activePestsList(resp: ActivePestsResponse | null | undefined): PestWindow[] {
  if (!resp || !Array.isArray(resp.active_pests)) return [];
  return resp.active_pests;
}

/** أشهر خطر نافذة كنصّ عربيّ مرتّب — للعرض المضغوط. */
export function riskMonthsText(win: PestWindow | null | undefined): string {
  if (!win || !Array.isArray(win.risk_months) || win.risk_months.length === 0) return DASH;
  return win.risk_months
    .filter((m) => Number.isInteger(m) && m >= 1 && m <= 12)
    .map((m) => monthNameAr(m))
    .join('، ') || DASH;
}

// ── توصية الموقع الجغرافيّ (geo-locate/recommend) ──────────────────────────

/** حقائق المناخ من مخرَج locate — الغائب يسقط (لا تصفير مجالات). */
export function geoRecommendFacts(resp: GeoRecommendResponse | null | undefined): DisplayFact[] {
  if (!resp?.supported) return [];
  const facts: DisplayFact[] = [];
  if (resp.governorate_ar) facts.push({ label: 'المحافظة', value: resp.governorate_ar });
  if (resp.zone_name_ar) facts.push({ label: 'الإقليم', value: resp.zone_name_ar });
  if (resp.climate_ar) facts.push({ label: 'المناخ', value: resp.climate_ar });
  if (Array.isArray(resp.temp_range_c) && resp.temp_range_c.length >= 2) {
    facts.push({ label: 'الحرارة', value: rangeText(resp.temp_range_c, '°م') });
  }
  if (Array.isArray(resp.annual_rain_mm) && resp.annual_rain_mm.length >= 2) {
    facts.push({ label: 'المطر السنويّ', value: rangeText(resp.annual_rain_mm, 'مم') });
  }
  if (Array.isArray(resp.humidity_pct) && resp.humidity_pct.length >= 2) {
    facts.push({ label: 'الرطوبة', value: rangeText(resp.humidity_pct, '٪') });
  }
  return facts;
}

/** قائمة نصّيّة من الخادم — بلا مصفوفة ⇒ [] (المحاصيل الملائمة/المتجنَّبة). */
export function stringList(list: string[] | null | undefined): string[] {
  if (!Array.isArray(list)) return [];
  return list.filter((s) => typeof s === 'string' && s.trim() !== '');
}

// ── ملخّص طقس الحقل (field-weather-summary) ────────────────────────────────

const OPERATION_AR: Record<string, string> = {
  spraying: 'الرشّ',
  harvesting: 'الحصاد',
  sowing: 'البذار',
  irrigation: 'الريّ',
};

/** تسمية عربيّة لعمليّة — الغريب يُعرَض كما جاء (لا نُخفي المجهول). */
export function operationLabelAr(op: string | null | undefined): string {
  if (!op) return DASH;
  return OPERATION_AR[op] || op;
}

/** لون الصلاحيّة — عقد الخادم (optimal/acceptable/poor/unsafe)؛ الغريب محايد. */
export function suitabilityColor(s: string | null | undefined): string {
  switch ((s || '').toLowerCase()) {
    case 'optimal':
      return '#86efac';
    case 'acceptable':
      return '#7dd3fc';
    case 'poor':
      return '#fdba74';
    case 'unsafe':
      return '#fca5a5';
    default:
      return '#64748b';
  }
}

/** تسمية عربيّة للصلاحيّة. */
export function suitabilityLabelAr(s: string | null | undefined): string {
  switch ((s || '').toLowerCase()) {
    case 'optimal':
      return 'مثاليّ';
    case 'acceptable':
      return 'مقبول';
    case 'poor':
      return 'ضعيف';
    case 'unsafe':
      return 'غير آمن';
    default:
      return s || DASH;
  }
}

/** صفوف صلاحيّة العمليّات من خريطة الخادم — بلا خريطة ⇒ []. */
export function operationRows(
  resp: FieldWeatherSummaryResponse | null | undefined,
): OperationSuitability[] {
  const ops = resp?.operations;
  if (!ops || typeof ops !== 'object') return [];
  return Object.values(ops).filter((o): o is OperationSuitability => !!o && typeof o.operation === 'string');
}

/** تنبيهات الطقس الحرجة كما صاغها الخادم — بلا مصفوفة ⇒ []. */
export function weatherAlerts(resp: FieldWeatherSummaryResponse | null | undefined): string[] {
  if (!resp || !Array.isArray(resp.alerts_ar)) return [];
  return resp.alerts_ar;
}

// ── تحليلات الطقس (weather-analytics) ──────────────────────────────────────

/** حقائق تحليل سجلّ الطقس — الحقول المحسوبة في الخادم، الغائب يسقط. */
export function analysisFacts(resp: WeatherAnalysisResponse | null | undefined): DisplayFact[] {
  if (!resp?.supported) return [];
  const facts: DisplayFact[] = [];
  if (resp.days_analyzed != null) facts.push({ label: 'أيّام محلَّلة', value: fmtNum(resp.days_analyzed) });
  if (resp.annual_rainfall_mm != null) facts.push({ label: 'المطر (سنويّاً)', value: `${fmtNum(resp.annual_rainfall_mm, 1)} مم` });
  if (resp.annual_et0_mm != null) facts.push({ label: 'ET₀ (سنويّاً)', value: `${fmtNum(resp.annual_et0_mm, 1)} مم` });
  if (resp.annual_water_deficit_mm != null) facts.push({ label: 'العجز المائيّ', value: `${fmtNum(resp.annual_water_deficit_mm, 1)} مم/سنة` });
  if (resp.heat_stress_days != null) facts.push({ label: 'أيّام إجهاد حراريّ', value: fmtNum(resp.heat_stress_days) });
  if (resp.severe_heat_days != null) facts.push({ label: 'أيّام حرّ شديد', value: fmtNum(resp.severe_heat_days) });
  if (resp.frost_days != null) facts.push({ label: 'أيّام صقيع', value: fmtNum(resp.frost_days) });
  if (resp.high_wind_days != null) facts.push({ label: 'أيّام رياح عالية', value: fmtNum(resp.high_wind_days) });
  return facts;
}

/** لون نافذة موسم الزراعة — عقد الخادم (optimal/transition/heat_stress). */
export function plantingWindowColor(window: string | null | undefined): string {
  switch ((window || '').toLowerCase()) {
    case 'optimal':
      return '#86efac';
    case 'transition':
      return '#fdba74';
    case 'heat_stress':
      return '#fca5a5';
    default:
      return '#64748b';
  }
}

/** أشهر دليل الزراعة كما رتّبها الخادم — بلا مصفوفة ⇒ []. */
export function plantingMonths(resp: PlantingGuideResponse | null | undefined): PlantingGuideMonth[] {
  if (!resp?.supported || !Array.isArray(resp.months)) return [];
  return resp.months;
}

/**
 * يحلّل سجلّ طقس يوميّ يُدخِله المستخدم (JSON) إلى مصفوفة سجلّات صالحة لِـanalyze.
 * صدق: لا تخمين — كلّ سجلّ يجب أن يحمل date + temp_max_c + temp_min_c رقميّين
 * (عقد analyze_weather_log). عند أيّ خلل نُرجِع رسالة صادقة بدل سجلّ مُلفَّق.
 */
export function parseWeatherRecords(
  raw: string,
): { records: WeatherRecord[] | null; error_ar: string | null } {
  const text = (raw || '').trim();
  if (text === '') return { records: null, error_ar: null };
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { records: null, error_ar: 'صيغة JSON غير صالحة — الصق مصفوفة سجلّات يوميّة.' };
  }
  if (!Array.isArray(parsed)) {
    return { records: null, error_ar: 'المتوقَّع مصفوفة سجلّات ([ … ]).' };
  }
  if (parsed.length === 0) {
    return { records: null, error_ar: 'السجلّ فارغ — أدخِل بيانات يوميّة.' };
  }
  const out: WeatherRecord[] = [];
  for (let i = 0; i < parsed.length; i += 1) {
    const r = parsed[i] as Record<string, unknown>;
    if (!r || typeof r !== 'object') {
      return { records: null, error_ar: `السجلّ رقم ${i + 1} ليس كائناً.` };
    }
    const tmax = Number(r.temp_max_c);
    const tmin = Number(r.temp_min_c);
    if (!Number.isFinite(tmax) || !Number.isFinite(tmin)) {
      return { records: null, error_ar: `السجلّ رقم ${i + 1} ينقصه temp_max_c/temp_min_c رقميّ.` };
    }
    const rec: WeatherRecord = {
      date: typeof r.date === 'string' ? r.date : '',
      temp_max_c: tmax,
      temp_min_c: tmin,
    };
    if (r.precipitation_mm != null && Number.isFinite(Number(r.precipitation_mm))) {
      rec.precipitation_mm = Number(r.precipitation_mm);
    }
    if (r.wind_speed_kmh != null && Number.isFinite(Number(r.wind_speed_kmh))) {
      rec.wind_speed_kmh = Number(r.wind_speed_kmh);
    }
    out.push(rec);
  }
  return { records: out, error_ar: null };
}

// ── استبيان التهيئة (onboarding) ───────────────────────────────────────────

/** أقسام الاستبيان كما عرّفها الخادم — بلا مصفوفة ⇒ []. */
export function questionnaireSections(
  resp: QuestionnaireResponse | null | undefined,
): OnboardingSectionDef[] {
  if (!resp || !Array.isArray(resp.sections)) return [];
  return resp.sections;
}

/** معرّفات الأسئلة الإلزاميّة عبر كلّ الأقسام (مرآة عقد الخادم required). */
export function requiredQuestionIds(
  resp: QuestionnaireResponse | null | undefined,
): string[] {
  return questionnaireSections(resp)
    .flatMap((s) => s.questions || [])
    .filter((q) => q.required === true)
    .map((q) => q.id);
}

/** هل القيمة «مُجابة»؟ يطابق عقد الخادم: ليست None/""/[] (validate_response). */
export function isAnswered(v: unknown): boolean {
  if (v == null) return false;
  if (typeof v === 'string') return v.trim() !== '';
  if (Array.isArray(v)) return v.length > 0;
  return true;
}

/**
 * الإلزاميّات الناقصة قبل الإرسال — معاينة عميل تُطابق validate_response للخادم
 * (الحكم النهائيّ من الخادم في missing_required بالردّ). لا نُخفي ولا نُرسِل زوراً.
 */
export function missingRequiredIds(
  resp: QuestionnaireResponse | null | undefined,
  answers: Record<string, unknown>,
): string[] {
  const a = answers || {};
  return requiredQuestionIds(resp).filter((id) => !isAnswered(a[id]));
}

/** عدد الإجابات الفعليّة (غير الفارغة) — مرآة answered في الخادم. */
export function answeredCount(answers: Record<string, unknown> | null | undefined): number {
  if (!answers) return 0;
  return Object.keys(answers).filter((k) => isAnswered(answers[k])).length;
}

/** يبني جسم POST /responses بصدق «يُرسَل المُدخَل» — يُسقِط القيم الفارغة. */
export function buildSubmitPayload(
  fieldId: string | null | undefined,
  answers: Record<string, unknown>,
): OnboardingSubmitPayload {
  const clean: Record<string, unknown> = {};
  const a = answers || {};
  for (const k of Object.keys(a)) {
    if (isAnswered(a[k])) clean[k] = a[k];
  }
  return { field_id: fieldId || null, answers: clean };
}
