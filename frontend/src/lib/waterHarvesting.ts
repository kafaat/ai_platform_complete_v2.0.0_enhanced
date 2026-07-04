// Water Harvesting + Irrigation Method — يعكس محرّكَي backend المُخزَّنَين بلا قارئ واجهة:
// /api/v1/water-harvesting/* (إمكانات حصاد المطر + الطرق التراثيّة اليمنيّة + دليل الطريقة)
// و/api/v1/irrigation-method (ملامح طرق الريّ — كفاءات FAO عامّة موسومة calibrated=false).
// صدق صارم: النصوص والأحكام كلّها من الخادم (advice_ar/note_ar/caution_ar/disclaimer_ar
// وwarnings_ar تمرّ حرفيّاً، لا يُعاد الحكم في الواجهة)؛ null ⇒ «—»؛ الغائب يسقط لا
// يُصفَّر؛ والقياسات (مساحة السطح/المطر السنويّ) يُدخِلها المستخدم من قياس حقيقيّ لا تُخمَّن.

// ── أشكال الاستجابة الحقيقيّة (services/sahool-platform/api/water_harvesting.py) ──

export interface HarvestPotentialResponse {
  supported: boolean;
  catchment_area_m2?: number;
  annual_rain_mm?: number;
  surface?: string;
  runoff_coefficient?: number;
  harvestable_liters?: number;
  harvestable_m3?: number;
  advice_ar?: string;
  note_ar?: string;
  message_ar?: string;
}

export interface HarvestMethodSummary {
  method: string;
  name_ar: string;
  what_ar: string;
  best_for_ar: string;
}

export interface HarvestingMethodsResponse {
  methods?: HarvestMethodSummary[];
  principle_ar?: string;
  yemen_note_ar?: string;
}

export interface MethodGuideResponse {
  supported: boolean;
  method?: string;
  name_ar?: string;
  what_ar?: string;
  benefits_ar?: string[];
  best_for_ar?: string;
  caution_ar?: string;
  disclaimer_ar?: string;
  message_ar?: string;
}

// ── أشكال ملامح طرق الريّ (services/sahool-platform/api/irrigation_method.py) ──

export interface IrrigationMethodProfile {
  method: string;
  method_ar: string;
  known: boolean;
  application_efficiency?: number | null;
  wetted_fraction?: number | null;
  ke_factor?: number | null;
  typical_max_application_mm?: number | null;
  pressurized?: boolean;
  calibrated?: boolean;
  warnings_ar?: string[];
}

export interface IrrigationMethodsResponse {
  methods?: IrrigationMethodProfile[];
}

export interface DisplayFact {
  label: string;
  value: string;
}

const DASH = '—';

/** تنسيق رقم للعرض — null/undefined/غير منتهٍ ⇒ «—» (لا تصفير). */
export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return v.toFixed(digits);
}

/** رسالة الخادم لاستجابة غير مدعومة — تمرّ كما جاءت (unsupported ⇒ message_ar). */
export function serverMessage(
  resp: { supported?: boolean; message_ar?: string } | null | undefined,
): string | null {
  if (!resp || resp.supported !== false) return null;
  return resp.message_ar ?? null;
}

/** حقائق إمكانات الحصاد من الشكل الحقيقيّ — الغائب يسقط، unsupported ⇒ []. */
export function potentialFacts(resp: HarvestPotentialResponse | null | undefined): DisplayFact[] {
  if (!resp?.supported) return [];
  const facts: DisplayFact[] = [];
  if (resp.harvestable_m3 != null) {
    facts.push({ label: 'القابل للحصاد', value: `${fmtNum(resp.harvestable_m3, 1)} م³/سنة` });
  }
  if (resp.harvestable_liters != null) {
    facts.push({ label: 'باللتر', value: `${fmtNum(resp.harvestable_liters)} لتر/سنة` });
  }
  if (resp.runoff_coefficient != null) {
    facts.push({ label: 'معامل الجريان', value: fmtNum(resp.runoff_coefficient, 2) });
  }
  return facts;
}

/** طرق الحصاد كما يرتّبها الخادم — بلا مصفوفة ⇒ [] بصدق. */
export function methodPills(resp: HarvestingMethodsResponse | null | undefined): HarvestMethodSummary[] {
  if (!resp || !Array.isArray(resp.methods)) return [];
  return resp.methods;
}

/** فوائد دليل الطريقة — unsupported/بلا مصفوفة ⇒ [] (message_ar عبر serverMessage). */
export function guideBenefits(resp: MethodGuideResponse | null | undefined): string[] {
  if (!resp?.supported || !Array.isArray(resp.benefits_ar)) return [];
  return resp.benefits_ar;
}

/** ملامح طرق الريّ كما يعيدها الخادم — بلا مصفوفة ⇒ []. */
export function irrigationProfiles(resp: IrrigationMethodsResponse | null | undefined): IrrigationMethodProfile[] {
  if (!resp || !Array.isArray(resp.methods)) return [];
  return resp.methods;
}

/** حقائق ملامح طريقة ريّ — أرقام الخادم كما هي (الكفاءة تُعرَض ٪ من كسر الخادم)،
 *  الغائب يسقط لا يُصفَّر، وpressurized حكم الخادم يُترجَم تسميةً فقط. */
export function profileFacts(p: IrrigationMethodProfile | null | undefined): DisplayFact[] {
  if (!p) return [];
  const facts: DisplayFact[] = [];
  if (p.application_efficiency != null) {
    facts.push({ label: 'كفاءة التطبيق', value: `${fmtNum(p.application_efficiency * 100)}٪` });
  }
  if (p.wetted_fraction != null) {
    facts.push({ label: 'نسبة البلل', value: fmtNum(p.wetted_fraction, 2) });
  }
  if (p.ke_factor != null) {
    facts.push({ label: 'معامل التبخّر Ke', value: fmtNum(p.ke_factor, 2) });
  }
  if (p.typical_max_application_mm != null) {
    facts.push({ label: 'سقف الدفعة', value: `${fmtNum(p.typical_max_application_mm)} مم` });
  }
  if (p.pressurized != null) {
    facts.push({ label: 'الطاقة', value: p.pressurized ? 'مضغوط (يحتاج ضخّاً)' : 'جاذبيّ' });
  }
  return facts;
}
