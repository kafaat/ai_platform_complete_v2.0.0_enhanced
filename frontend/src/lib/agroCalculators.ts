// Agro Calculators — بناة مُدخلات حاسبات القياس الحقليّة (بذور · ما بعد الحصاد · بنّ)
// لنقاط GET الصرفة: /api/v1/seed/germination-rate · storage-check · sowing-depth · criteria
// و/api/v1/postharvest/moisture-check و/api/v1/coffee/site-suitability.
// صدق (نمط ledgerEntry): تحقّق صارم محليّاً قبل الاستدعاء — أرقام منتهية ضمن مداها،
// حقول إلزاميّة — نرفض برسالة عربيّة واضحة بدل استدعاء بقيم فاسدة أو تلفيق أصفار؛
// الخادم يبقى الحكم النهائيّ (منطقه في api/seed_and_practices · postharvest_advisor · coffee_advisor).

export type BuildResult<T> = { ok: true; payload: T } | { ok: false; error: string };

/** رقم منتهٍ من نصّ/رقم — أو رسالة خطأ عربيّة. */
function finiteNumber(value: string | number | null | undefined, label: string): number | string {
  const raw = typeof value === 'number' ? value : String(value ?? '').trim();
  if (raw === '') return `${label} مطلوب.`;
  const n = typeof raw === 'number' ? raw : Number(raw);
  if (!Number.isFinite(n)) return `${label} يجب أن يكون رقماً صحيح الصياغة.`;
  return n;
}

// ---------------------------------------------------------------------------
// 1) معدّل الإنبات — GET /api/v1/seed/germination-rate?sprouted&total
// ---------------------------------------------------------------------------

export interface GerminationParams {
  sprouted: number;
  total: number;
}

/** استجابة الخادم: supported=false ترجع message_ar فقط (تُعرَض كما هي). */
export interface GerminationRateResponse {
  supported: boolean;
  message_ar?: string;
  sprouted?: number;
  total?: number;
  germination_pct?: number;
  verdict_ar?: string;
  method_ar?: string;
  disclaimer_ar?: string;
}

export function buildGerminationParams(input: {
  sprouted: string | number;
  total: string | number;
}): BuildResult<GerminationParams> {
  const sprouted = finiteNumber(input.sprouted, 'عدد البذور المُنبِتة');
  if (typeof sprouted === 'string') return { ok: false, error: sprouted };
  const total = finiteNumber(input.total, 'إجمالي بذور العيّنة');
  if (typeof total === 'string') return { ok: false, error: total };
  if (!Number.isInteger(sprouted) || !Number.isInteger(total)) {
    return { ok: false, error: 'الأعداد يجب أن تكون صحيحة (بذور تُعَدّ عدّاً).' };
  }
  if (total <= 0) return { ok: false, error: 'إجمالي بذور العيّنة يجب أن يكون عدداً موجباً.' };
  if (sprouted < 0) return { ok: false, error: 'عدد البذور المُنبِتة لا يكون سالباً.' };
  if (sprouted > total) return { ok: false, error: 'المُنبِت لا يتجاوز إجمالي العيّنة.' };
  return { ok: true, payload: { sprouted, total } };
}

// ---------------------------------------------------------------------------
// 2) قاعدة المئة لتخزين البذور — GET /api/v1/seed/storage-check?temp_f&humidity_pct
// ---------------------------------------------------------------------------

export interface StorageCheckParams {
  temp_f: number;
  humidity_pct: number;
}

export interface SeedStorageCheckResponse {
  temp_f: number;
  humidity_pct: number;
  sum: number;
  good_storage: boolean;
  verdict_ar: string;
  rule_ar: string;
  tip_ar: string;
  disclaimer_ar: string;
}

/** الحرارة تُدخَل بالمئويّة (قياس المزارع) وتُحوَّل لفهرنهايت لأنّ قاعدة الخادم بها. */
export function buildStorageCheckParams(input: {
  tempC: string | number;
  humidityPct: string | number;
}): BuildResult<StorageCheckParams> {
  const tempC = finiteNumber(input.tempC, 'درجة حرارة المخزن (°م)');
  if (typeof tempC === 'string') return { ok: false, error: tempC };
  if (tempC < -30 || tempC > 60) {
    return { ok: false, error: 'درجة حرارة المخزن خارج المدى الواقعي (-30 إلى 60°م).' };
  }
  const humidity = finiteNumber(input.humidityPct, 'الرطوبة النسبيّة %');
  if (typeof humidity === 'string') return { ok: false, error: humidity };
  if (humidity < 0 || humidity > 100) {
    return { ok: false, error: 'الرطوبة النسبيّة تكون بين 0 و100%.' };
  }
  return {
    ok: true,
    payload: { temp_f: Math.round((tempC * 9) / 5 + 32), humidity_pct: humidity },
  };
}

// ---------------------------------------------------------------------------
// 3) عمق البذر — GET /api/v1/seed/sowing-depth?seed_size_mm&precision
// ---------------------------------------------------------------------------

export interface SowingDepthParams {
  seed_size_mm: number;
  precision: boolean;
}

export interface SowingDepthResponse {
  supported: boolean;
  message_ar?: string;
  seed_size_mm?: number;
  recommended_depth_mm?: number;
  factor?: number;
  advice_ar?: string;
  principle_ar?: string;
  note_ar?: string;
  disclaimer_ar?: string;
}

export function buildSowingDepthParams(input: {
  seedSizeMm: string | number;
  precision?: boolean;
}): BuildResult<SowingDepthParams> {
  const size = finiteNumber(input.seedSizeMm, 'حجم البذرة (مم)');
  if (typeof size === 'string') return { ok: false, error: size };
  if (size <= 0) return { ok: false, error: 'حجم البذرة يجب أن يكون رقماً موجباً (مم).' };
  if (size > 100) return { ok: false, error: 'حجم بذرة غير واقعي (>100 مم) — تأكّد من الوحدة.' };
  return { ok: true, payload: { seed_size_mm: size, precision: input.precision === true } };
}

// ---------------------------------------------------------------------------
// 4) معايير اختيار البذور — GET /api/v1/seed/criteria (بلا مُدخلات)
// ---------------------------------------------------------------------------

export interface SeedCriteriaResponse {
  criteria_ar: { factor_ar: string; detail_ar: string }[];
  improved_seed_benefit_ar: string;
  source_guidance_ar: string;
  caution_ar: string;
  disclaimer_ar: string;
}

// ---------------------------------------------------------------------------
// 5) رطوبة التخزين للحبوب — GET /api/v1/postharvest/moisture-check?crop&moisture_pct
// ---------------------------------------------------------------------------

export interface MoistureCheckParams {
  crop: string;
  moisture_pct: number;
}

/** supported=false يعني محصولاً بلا عتبة معروفة — message_ar تعدّد المدعوم. */
export interface MoistureCheckResponse {
  supported: boolean;
  message_ar?: string;
  crop_ar?: string;
  moisture_pct?: number;
  safe_max_pct?: number;
  status?: string;
  status_ar?: string;
  advice_ar?: string;
}

export function buildMoistureCheckParams(input: {
  crop: string | null | undefined;
  moisturePct: string | number;
}): BuildResult<MoistureCheckParams> {
  const crop = String(input.crop ?? '').trim();
  if (!crop) return { ok: false, error: 'اسم المحصول مطلوب (قمح، ذرة…).' };
  const moisture = finiteNumber(input.moisturePct, 'رطوبة الحبوب %');
  if (typeof moisture === 'string') return { ok: false, error: moisture };
  if (moisture <= 0 || moisture > 100) {
    return { ok: false, error: 'رطوبة الحبوب تكون بين 0 و100% (من جهاز قياس الرطوبة).' };
  }
  return { ok: true, payload: { crop, moisture_pct: moisture } };
}

// ---------------------------------------------------------------------------
// 6) ملاءمة موقع للبنّ — GET /api/v1/coffee/site-suitability?altitude_m
// ---------------------------------------------------------------------------

export interface CoffeeSiteParams {
  altitude_m: number;
}

export interface CoffeeSiteResponse {
  altitude_m: number;
  rating: string;
  rating_ar: string;
  reason_ar: string;
  optimal_range_ar: string;
}

export function buildCoffeeSiteParams(input: {
  altitudeM: string | number;
}): BuildResult<CoffeeSiteParams> {
  const alt = finiteNumber(input.altitudeM, 'الارتفاع عن سطح البحر (م)');
  if (typeof alt === 'string') return { ok: false, error: alt };
  if (alt < 0) return { ok: false, error: 'الارتفاع لا يكون سالباً (بالأمتار فوق سطح البحر).' };
  if (alt > 3700) {
    return { ok: false, error: 'ارتفاع يتجاوز أعلى قمم اليمن (~3666م) — تأكّد من القيمة.' };
  }
  return { ok: true, payload: { altitude_m: alt } };
}

// ---------------------------------------------------------------------------
// ألوان الحالات — للحالات المعروفة من الخادم فقط؛ المجهول يبقى محايداً (null).
// ---------------------------------------------------------------------------

const MOISTURE_STATUS_COLORS: Record<string, string> = {
  safe: '#86efac', //  ✓ آمنة
  risky: '#fdba74', // ⚠ حدّيّة
  unsafe: '#fca5a5', // ✗ غير آمنة
};

const COFFEE_RATING_COLORS: Record<string, string> = {
  optimal: '#86efac',
  suitable: '#86efac',
  marginal: '#fdba74',
  unsuitable: '#fca5a5',
};

/** لون حالة رطوبة التخزين — أو null لحالة غير معروفة (لا نخمّن). */
export function moistureStatusColor(status: string | null | undefined): string | null {
  return (status && MOISTURE_STATUS_COLORS[status]) || null;
}

/** لون تقييم ملاءمة موقع البنّ — أو null لتقييم غير معروف. */
export function coffeeRatingColor(rating: string | null | undefined): string | null {
  return (rating && COFFEE_RATING_COLORS[rating]) || null;
}
