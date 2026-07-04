// What-If Scenarios — بناة حمولات سيناريوهات «ماذا لو» الفيزيائيّة + أنواع الاستجابة
// لنقاط POST /api/v1/scenario/{temperature|rainfall|planting-date|water-twin}
// (services/sahool-platform/api/routers/scenario.py). صدق جذريّ:
//   • الخادم حساب فيزيائيّ offline (FAO-56/GDD) — لا توأم رقميّ ولا ML ولا غلّة مُلفّقة
//     (api/scenario_whatif.py · api/water_twin.py). لا يُرجِع حقل `calibrated` — إخلاء
//     المسؤوليّة يأتي نصّاً داخل `summary_ar` ويجب عرضه كما هو، مع لافتة ثابتة أدناه.
//   • تحقّق محلّيّ صارم برسائل عربيّة (نمط BuildResult من ledgerEntry.ts) قبل الإرسال —
//     نرفض بوضوح بدل 422 غامضة؛ والخادم يبقى الحكم النهائيّ.
//   • لا دلتا مُلفّقة في الواجهة: المقارنات كلّها من `comparisons` الخادميّة؛ null ⇒ «—».

import type { BuildResult } from './ledgerEntry';

export type { BuildResult };

// ── ثوابت العقد ───────────────────────────────────────────────────────────────
export const SCENARIO_ENDPOINTS = {
  temperature: '/api/v1/scenario/temperature',
  rainfall: '/api/v1/scenario/rainfall',
  plantingDate: '/api/v1/scenario/planting-date',
  waterTwin: '/api/v1/scenario/water-twin',
} as const;

/** لافتة الصدق الثابتة — تُعرَض مع كلّ نتيجة (الخادم يكرّرها نصّيّاً في summary_ar). */
export const UNCALIBRATED_NOTE_AR =
  'محاكاة افتراضات — ليست تنبّؤاً معايَراً؛ حساب فيزيائيّ (FAO-56/GDD) للاستبصار، والقرار للمزارع.';

/** محاصيل GDD المدعومة خادميّاً — planting-date يرفض غيرها بـ422
 *  (api/gdd_tracker.py:GDD_CROP_PARAMS). */
export const GDD_CROPS = ['wheat', 'barley', 'sorghum', 'tomato', 'maize'] as const;

/** محاصيل جدول Kc (api/water_balance.py:KC_BY_CROP_STAGE) — غير المعروف يسقط
 *  لِـKc عامّ خادميّاً (لا رفض)، لكنّ القائمة تُرشد الاختيار. */
export const WATER_CROPS = [
  'wheat', 'barley', 'sorghum', 'maize', 'millet', 'tomato',
  'potato', 'onion', 'alfalfa', 'citrus', 'dates',
] as const;

export const STAGES = ['initial', 'development', 'mid', 'late'] as const;

export const CROP_AR: Record<string, string> = {
  wheat: 'قمح', barley: 'شعير', sorghum: 'ذرة رفيعة', maize: 'ذرة شاميّة', millet: 'دخن',
  tomato: 'طماطم', potato: 'بطاطس', onion: 'بصل', alfalfa: 'برسيم', citrus: 'حمضيّات', dates: 'نخيل',
};
export const STAGE_AR: Record<string, string> = {
  initial: 'ابتدائيّة', development: 'نموّ', mid: 'منتصف', late: 'نهاية',
};

/** استدلال مفتاح المحصول من التسمية العربيّة للحقل (مثل «قمح صلب») — بلا تخمين:
 *  غير المطابق ⇒ null (الواجهة تترك الاختيار للمستخدم). الترتيب مهمّ (ذرة رفيعة قبل ذرة). */
export function cropKeyFromLabel(label: string | null | undefined): string | null {
  const s = (label ?? '').trim();
  if (!s) return null;
  const pairs: [string, string][] = [
    ['قمح', 'wheat'], ['شعير', 'barley'], ['ذرة رفيعة', 'sorghum'], ['ذرة شامية', 'maize'],
    ['ذرة شاميّة', 'maize'], ['ذرة', 'maize'], ['دخن', 'millet'], ['طماطم', 'tomato'],
    ['بندورة', 'tomato'], ['بطاط', 'potato'], ['بصل', 'onion'], ['برسيم', 'alfalfa'],
    ['حمضي', 'citrus'], ['برتقال', 'citrus'], ['ليمون', 'citrus'], ['نخيل', 'dates'], ['تمر', 'dates'],
  ];
  for (const [needle, key] of pairs) if (s.includes(needle)) return key;
  return null;
}

// ── أنواع الاستجابة (مطابقة حرفيّاً لأشكال return الخادميّة) ─────────────────────
/** صفّ مقارنة أساس/بديل — ScenarioComparison.to_dict() (api/scenario_whatif.py:37). */
export interface ScenarioComparison {
  metric_ar: string;
  baseline: number;
  scenario: number;
  delta: number;
  unit: string;
}

/** POST /scenario/temperature — whatif_temperature_shift (api/scenario_whatif.py:95). */
export interface TemperatureScenarioResult {
  scenario_type: 'temperature_shift';
  comparisons: ScenarioComparison[];
  /** يتضمّن نصّ الصدق الخادميّ: «حساب فيزيائي — للاستبصار لا للتنفيذ الآلي.» */
  summary_ar: string;
}

/** POST /scenario/rainfall — whatif_rainfall_change (api/scenario_whatif.py:181). */
export interface RainfallScenarioResult {
  scenario_type: 'rainfall_change';
  comparisons: ScenarioComparison[];
  summary_ar: string;
}

/** POST /scenario/planting-date — whatif_planting_date (api/scenario_whatif.py:139). */
export interface PlantingScenarioResult {
  scenario_type: 'planting_date';
  comparisons: ScenarioComparison[];
  baseline_stage: string;
  scenario_stage: string;
  summary_ar: string;
}

/** حالة يوم في مسار توأم المياه — DayState.to_dict() (api/water_twin.py:45). */
export interface WaterTwinDayState {
  day: number;
  depletion_mm: number;
  soil_moisture_pct: number;
  ks: number;
  eta_mm: number;
  stressed: boolean;
}

/** مُلخّص مسار — TrajectorySummary.to_dict() (api/water_twin.py:69). */
export interface WaterTwinTrajectory {
  days: number;
  total_irrigation_mm: number;
  total_eta_mm: number;
  stress_days: number;
  max_depletion_mm: number;
  final_depletion_mm: number;
  final_soil_moisture_pct: number;
  states: WaterTwinDayState[];
}

/** POST /scenario/water-twin — compare_scenarios (api/water_twin.py:231). صدق:
 *  المقارنة على أيّام الإجهاد/النضوب/الماء فقط — الخادم لا يقدّر الغلّة (غير مُنمذَجة). */
export interface WaterTwinScenarioResult {
  scenario_type: 'water_twin_trajectory';
  baseline: WaterTwinTrajectory;
  scenario: WaterTwinTrajectory;
  comparisons: ScenarioComparison[];
  summary_ar: string;
}

// ── أنواع الحمولات (مطابقة لنماذج Pydantic الخادميّة) ───────────────────────────
/** WhatIfTempRequest (api/api_models.py:492) — lat/elev/doy لها افتراضات خادميّة؛
 *  لا نكرّرها محلّيّاً: تُرسَل فقط إذا أدخلها المستخدم. */
export interface TemperatureScenarioPayload {
  crop: string;
  stage: string;
  t_min_c: number;
  t_max_c: number;
  temp_shift_c: number;
  rain_mm?: number;
  latitude_deg?: number;
  elevation_m?: number;
  day_of_year?: number;
}

/** WhatIfRainRequest (api/api_models.py:510). */
export interface RainfallScenarioPayload {
  crop: string;
  stage: string;
  t_min_c: number;
  t_max_c: number;
  rain_baseline_mm: number;
  rain_scenario_mm: number;
  latitude_deg?: number;
  elevation_m?: number;
  day_of_year?: number;
}

/** WhatIfPlantingRequest (api/api_models.py:504). */
export interface PlantingScenarioPayload {
  crop: string;
  temps_baseline: { t_min_c: number; t_max_c: number }[];
  temps_scenario: { t_min_c: number; t_max_c: number }[];
}

/** WaterTwinRequest (routers/scenario.py:59) — kind=delay|scale من الواجهة
 *  (explicit يتطلّب جدولاً يوميّاً كاملاً — خارج نطاق هذه البطاقة). */
export interface WaterTwinScenarioPayload {
  taw_mm: number;
  raw_mm: number;
  initial_depletion_mm: number;
  days: { etc_mm: number; rain_mm: number; irrigation_mm: number }[];
  scenario_kind: 'delay' | 'scale';
  delay_days?: number;
  scale_factor?: number;
}

// ── تحقّق مشترك ────────────────────────────────────────────────────────────────
function num(value: string | number | null | undefined, label: string): number | string {
  const n = typeof value === 'number' ? value : Number(String(value ?? '').trim());
  if (String(value ?? '').trim() === '' && typeof value !== 'number') return `${label} مطلوب.`;
  if (!Number.isFinite(n)) return `${label}: أدخل رقماً صالحاً.`;
  return n;
}

function nonNegative(value: string | number | null | undefined, label: string): number | string {
  const n = num(value, label);
  if (typeof n === 'string') return n;
  if (n < 0) return `${label} يجب ألّا يكون سالباً.`;
  return n;
}

function intInRange(
  value: string | number | null | undefined, label: string, min: number, max: number,
): number | string {
  const n = num(value, label);
  if (typeof n === 'string') return n;
  if (!Number.isInteger(n) || n < min || n > max)
    return `${label} يجب أن يكون عدداً صحيحاً بين ${min} و${max}.`;
  return n;
}

/** يتحقّق من زوج حرارة (دنيا ≤ قصوى) ويعيد الزوج أو رسالة عربيّة. */
function tempPair(
  tMin: string | number | null | undefined,
  tMax: string | number | null | undefined,
  labelPrefix: string,
): { t_min_c: number; t_max_c: number } | string {
  const lo = num(tMin, `${labelPrefix}: الحرارة الدنيا`);
  if (typeof lo === 'string') return lo;
  const hi = num(tMax, `${labelPrefix}: الحرارة القصوى`);
  if (typeof hi === 'string') return hi;
  if (lo > hi) return `${labelPrefix}: الحرارة الدنيا (${lo}°) أعلى من القصوى (${hi}°).`;
  return { t_min_c: lo, t_max_c: hi };
}

/** حقول الموقع الاختياريّة (تُرسَل فقط إذا أُدخلت — افتراضات الخادم تبقى مرجعاً). */
function optionalSite(
  input: { latitudeDeg?: string | number | null; elevationM?: string | number | null; dayOfYear?: string | number | null },
  payload: { latitude_deg?: number; elevation_m?: number; day_of_year?: number },
): string | null {
  if (input.latitudeDeg != null && String(input.latitudeDeg).trim() !== '') {
    const lat = num(input.latitudeDeg, 'خطّ العرض');
    if (typeof lat === 'string') return lat;
    if (lat < -90 || lat > 90) return 'خطّ العرض يجب أن يكون بين −90 و90.';
    payload.latitude_deg = lat;
  }
  if (input.elevationM != null && String(input.elevationM).trim() !== '') {
    const elev = num(input.elevationM, 'الارتفاع (م)');
    if (typeof elev === 'string') return elev;
    payload.elevation_m = elev;
  }
  if (input.dayOfYear != null && String(input.dayOfYear).trim() !== '') {
    const doy = intInRange(input.dayOfYear, 'يوم السنة', 1, 366);
    if (typeof doy === 'string') return doy;
    payload.day_of_year = doy;
  }
  return null;
}

// ── بناة الحمولات ─────────────────────────────────────────────────────────────
export interface TemperatureScenarioInput {
  crop: string;
  stage: string;
  tMinC: string | number;
  tMaxC: string | number;
  /** افتراض المستخدم: تحوّل الحرارة (±°C) — صفر لا يشكّل سيناريو. */
  tempShiftC: string | number;
  rainMm?: string | number;
  latitudeDeg?: string | number | null;
  elevationM?: string | number | null;
  dayOfYear?: string | number | null;
}

export function buildTemperaturePayload(
  input: TemperatureScenarioInput,
): BuildResult<TemperatureScenarioPayload> {
  if (!input.crop.trim()) return { ok: false, error: 'المحصول مطلوب.' };
  if (!(STAGES as readonly string[]).includes(input.stage))
    return { ok: false, error: 'مرحلة النموّ مطلوبة (initial/development/mid/late).' };
  const pair = tempPair(input.tMinC, input.tMaxC, 'حرارة اليوم');
  if (typeof pair === 'string') return { ok: false, error: pair };
  const shift = num(input.tempShiftC, 'تحوّل الحرارة (±°C)');
  if (typeof shift === 'string') return { ok: false, error: shift };
  if (shift === 0) return { ok: false, error: 'تحوّل الحرارة صفر — لا سيناريو للمقارنة.' };
  const payload: TemperatureScenarioPayload = {
    crop: input.crop.trim(), stage: input.stage, ...pair, temp_shift_c: shift,
  };
  if (input.rainMm != null && String(input.rainMm).trim() !== '') {
    const rain = nonNegative(input.rainMm, 'المطر (مم)');
    if (typeof rain === 'string') return { ok: false, error: rain };
    payload.rain_mm = rain;
  }
  const siteErr = optionalSite(input, payload);
  if (siteErr) return { ok: false, error: siteErr };
  return { ok: true, payload };
}

export interface RainfallScenarioInput {
  crop: string;
  stage: string;
  tMinC: string | number;
  tMaxC: string | number;
  rainBaselineMm: string | number;
  /** افتراض المستخدم: المطر البديل (مم). */
  rainScenarioMm: string | number;
  latitudeDeg?: string | number | null;
  elevationM?: string | number | null;
  dayOfYear?: string | number | null;
}

export function buildRainfallPayload(
  input: RainfallScenarioInput,
): BuildResult<RainfallScenarioPayload> {
  if (!input.crop.trim()) return { ok: false, error: 'المحصول مطلوب.' };
  if (!(STAGES as readonly string[]).includes(input.stage))
    return { ok: false, error: 'مرحلة النموّ مطلوبة (initial/development/mid/late).' };
  const pair = tempPair(input.tMinC, input.tMaxC, 'حرارة اليوم');
  if (typeof pair === 'string') return { ok: false, error: pair };
  const base = nonNegative(input.rainBaselineMm, 'مطر الأساس (مم)');
  if (typeof base === 'string') return { ok: false, error: base };
  const scen = nonNegative(input.rainScenarioMm, 'مطر الافتراض (مم)');
  if (typeof scen === 'string') return { ok: false, error: scen };
  if (base === scen) return { ok: false, error: 'قيمتا المطر متساويتان — لا سيناريو للمقارنة.' };
  const payload: RainfallScenarioPayload = {
    crop: input.crop.trim(), stage: input.stage, ...pair,
    rain_baseline_mm: base, rain_scenario_mm: scen,
  };
  const siteErr = optionalSite(input, payload);
  if (siteErr) return { ok: false, error: siteErr };
  return { ok: true, payload };
}

export interface PlantingScenarioInput {
  crop: string;
  /** نافذة المقارنة بالأيّام — تُوسَّع لسلسلة يوميّة ثابتة (افتراض مُصرَّح به لا قياس). */
  horizonDays: string | number;
  baselineTMinC: string | number;
  baselineTMaxC: string | number;
  scenarioTMinC: string | number;
  scenarioTMaxC: string | number;
}

export function buildPlantingPayload(
  input: PlantingScenarioInput,
): BuildResult<PlantingScenarioPayload> {
  const crop = input.crop.trim();
  if (!(GDD_CROPS as readonly string[]).includes(crop)) {
    // الخادم يرفض بـ422 «محصول غير معروف لـGDD» — نرفض مبكّراً بقائمة المدعوم.
    const supported = GDD_CROPS.map((c) => CROP_AR[c] ?? c).join('، ');
    return { ok: false, error: `محصول غير مدعوم لحساب GDD. المدعوم: ${supported}.` };
  }
  const days = intInRange(input.horizonDays, 'نافذة المقارنة (يوم)', 1, 366);
  if (typeof days === 'string') return { ok: false, error: days };
  const basePair = tempPair(input.baselineTMinC, input.baselineTMaxC, 'موعد الأساس');
  if (typeof basePair === 'string') return { ok: false, error: basePair };
  const scenPair = tempPair(input.scenarioTMinC, input.scenarioTMaxC, 'الموعد البديل');
  if (typeof scenPair === 'string') return { ok: false, error: scenPair };
  return {
    ok: true,
    payload: {
      crop,
      temps_baseline: Array.from({ length: days }, () => ({ ...basePair })),
      temps_scenario: Array.from({ length: days }, () => ({ ...scenPair })),
    },
  };
}

export interface WaterTwinScenarioInput {
  tawMm: string | number;
  rawMm: string | number;
  initialDepletionMm?: string | number;
  /** أفق المحاكاة بالأيّام (جدول أساس ثابت يُبنى منه). */
  horizonDays: string | number;
  dailyEtcMm: string | number;
  dailyRainMm?: string | number;
  /** عمق الريّة الواحدة (مم) وتكرارها كلّ K أيّام — جدول الأساس. */
  irrigationDepthMm: string | number;
  irrigationIntervalDays: string | number;
  kind: 'delay' | 'scale';
  delayDays?: string | number;
  scaleFactor?: string | number;
}

export function buildWaterTwinPayload(
  input: WaterTwinScenarioInput,
): BuildResult<WaterTwinScenarioPayload> {
  const taw = num(input.tawMm, 'TAW (مم)');
  if (typeof taw === 'string') return { ok: false, error: taw };
  if (taw <= 0) return { ok: false, error: 'TAW يجب أن يكون موجباً (مم).' };
  const raw = num(input.rawMm, 'RAW (مم)');
  if (typeof raw === 'string') return { ok: false, error: raw };
  if (raw <= 0 || raw > taw) return { ok: false, error: 'RAW يجب أن يكون موجباً ولا يتجاوز TAW.' };
  const dep0 = input.initialDepletionMm == null || String(input.initialDepletionMm).trim() === ''
    ? 0
    : num(input.initialDepletionMm, 'النضوب الابتدائيّ (مم)');
  if (typeof dep0 === 'string') return { ok: false, error: dep0 };
  if (dep0 < 0 || dep0 > taw)
    return { ok: false, error: 'النضوب الابتدائيّ يجب أن يكون بين 0 وTAW.' };
  const horizon = intInRange(input.horizonDays, 'أفق المحاكاة (يوم)', 1, 120);
  if (typeof horizon === 'string') return { ok: false, error: horizon };
  const etc = nonNegative(input.dailyEtcMm, 'ETc اليوميّ (مم)');
  if (typeof etc === 'string') return { ok: false, error: etc };
  const rain = input.dailyRainMm == null || String(input.dailyRainMm).trim() === ''
    ? 0
    : nonNegative(input.dailyRainMm, 'المطر اليوميّ (مم)');
  if (typeof rain === 'string') return { ok: false, error: rain };
  const depth = nonNegative(input.irrigationDepthMm, 'عمق الريّة (مم)');
  if (typeof depth === 'string') return { ok: false, error: depth };
  const interval = intInRange(input.irrigationIntervalDays, 'تكرار الريّ (كلّ كم يوم)', 1, 120);
  if (typeof interval === 'string') return { ok: false, error: interval };

  const payload: WaterTwinScenarioPayload = {
    taw_mm: taw,
    raw_mm: raw,
    initial_depletion_mm: dep0,
    // جدول الأساس: ETc/مطر ثابتان + ريّة بعمق depth كلّ interval أيّام (افتراض مُصرَّح به).
    days: Array.from({ length: horizon }, (_, i) => ({
      etc_mm: etc,
      rain_mm: rain,
      irrigation_mm: (i + 1) % interval === 0 ? depth : 0,
    })),
    scenario_kind: input.kind,
  };
  if (input.kind === 'delay') {
    const delay = intInRange(input.delayDays, 'أيّام تأجيل الريّ', 1, 120);
    if (typeof delay === 'string') return { ok: false, error: delay };
    payload.delay_days = delay;
  } else {
    const factor = nonNegative(input.scaleFactor, 'معامل عمق الريّ');
    if (typeof factor === 'string') return { ok: false, error: factor };
    if (factor === 1) return { ok: false, error: 'معامل 1.0 لا يغيّر جدول الريّ — لا سيناريو للمقارنة.' };
    payload.scale_factor = factor;
  }
  return { ok: true, payload };
}

// ── عرض صادق ──────────────────────────────────────────────────────────────────
/** رقم للعرض؛ الغائب/غير المنتهي ⇒ «—» (لا صفر مُلفَّق). */
export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
  const r = Number(v.toFixed(digits));
  return String(r);
}

/** دلتا بإشارة صريحة؛ الغائب ⇒ «—». الدلتا تأتي من الخادم فقط — لا تُحسَب هنا. */
export function fmtDelta(v: number | null | undefined, digits = 2): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
  const r = Number(v.toFixed(digits));
  return r > 0 ? `+${r}` : String(r);
}

/** تحويل حتميّ: مم على مساحة (هكتار) ⇒ م³ (1 مم/هكتار = 10 م³). مساحة غائبة ⇒ null (لا تخمين). */
export function mmToCubicMeters(mm: number | null | undefined, areaHa: number | null | undefined): number | null {
  if (typeof mm !== 'number' || !Number.isFinite(mm)) return null;
  if (typeof areaHa !== 'number' || !Number.isFinite(areaHa) || areaHa <= 0) return null;
  return Math.round(mm * 10 * areaHa * 100) / 100;
}
