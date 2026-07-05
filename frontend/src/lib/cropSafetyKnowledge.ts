// Crop Safety & Knowledge — يعكس نقاط backend اليتيمة (P1) بلا قارئ واجهة:
//   /api/v1/chemical-safety/check + /api/v1/chemical-safety/banned (routers/chemical_safety.py)
//   /api/v1/planting/crops + /api/v1/planting/window               (routers/planting.py)
//   /api/v1/postharvest/pests                                      (routers/postharvest.py)
//   /api/v1/high-value-crops/detail                                (routers/high_value_crops.py)
//   /api/v1/niche-crops/detail                                     (routers/niche_crops.py)
//   /api/v1/introduction/candidates                                (routers/introduction.py)
//
// صدق صارم — وخاصّة السلامة الكيميائيّة: حكم الخادم (status/status_ar/message_ar)
// يمرّ حرفيّاً ولا يُعاد الحكم في الواجهة أبداً (فحص/تحذير، لا أتمتة — مبدأ
// api/chemical_safety.py نفسه). null/غائب ⇒ «—» أو يسقط (لا تصفير ولا تلفيق).
// خرائط القيم المعروفة هنا للتلوين العرضيّ فقط، والمجهول ⇒ محايد #64748b.

// ── أشكال الاستجابة الحقيقيّة كما يعيدها الخادم ─────────────────────────────

/** جسم POST /api/v1/chemical-safety/check (api_models.py: ChemicalCheckRequest). */
export interface ChemicalCheckInput {
  chemical: string;
  dose_kg_ha?: number | null;
}

/** api/chemical_safety.py — ChemicalCheck.to_dict(): الحكم كلّه من الخادم. */
export interface ChemicalCheckResponse {
  status?: string; // ok | blocked | warning — حكم الخادم لا يُعاد
  status_ar?: string;
  chemical?: string;
  message_ar?: string;
  severity?: string | null;
  max_kg_ha?: number | null;
  buffer_zone_m?: number | null;
  reentry_hours?: number | null;
  /** 404 من الخادم ⇒ الميزة غير مُفعَّلة — حالة صادقة لا خطأ مُفزِع. */
  disabled?: boolean;
}

/** api/chemical_safety.py — list_banned(). */
export interface BannedChemicalRow {
  name?: string;
  reason_ar?: string;
  severity?: string;
}
export interface BannedChemicalsResponse {
  source_ar?: string;
  disclaimer_ar?: string;
  count?: number;
  chemicals?: BannedChemicalRow[];
  disabled?: boolean;
}

/** api/planting_calendar.py — supported_crops() (تحت مفتاح crops من الراوتر). */
export interface PlantingCropRow {
  crop: string;
  name_ar?: string;
  season_ar?: string;
  window_ar?: string;
}
export interface PlantingCropsResponse {
  crops?: PlantingCropRow[];
  disabled?: boolean;
}

/** api/planting_calendar.py — planting_window(): supported=false ⇒ message_ar فقط. */
export interface PlantingWindowResponse {
  supported?: boolean;
  message_ar?: string;
  crop?: string;
  crop_ar?: string;
  season_ar?: string;
  window_months?: number[];
  window_ar?: string;
  optimal_ar?: string;
  harvest_ar?: string;
  early_risk_ar?: string;
  late_risk_ar?: string;
  yemen_note_ar?: string;
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** api/postharvest_advisor.py — storage_pests(). */
export interface StoragePestRow {
  name_ar?: string;
  scientific?: string;
  note_ar?: string;
}
export interface StoragePestsResponse {
  pests?: StoragePestRow[];
  note_ar?: string;
  disabled?: boolean;
}

/** api/high_value_crops.py — high_value_crop_detail(): حقول مثبتة/بحذر/غير مناسبة
 *  تختلف حسب الفئة — كلّها اختياريّة والغائب يسقط. */
export interface HighValueCropDetailResponse {
  supported?: boolean;
  message_ar?: string;
  name_ar?: string;
  tier_ar?: string;
  type_ar?: string;
  value_ar?: string;
  water_ar?: string;
  salinity_ar?: string;
  yield_ar?: string;
  opportunity_ar?: string;
  evidence_ar?: string;
  note_ar?: string;
  fit_ar?: string;
  reason_ar?: string;
  caution_ar?: string;
  disabled?: boolean;
}

/** api/niche_export_crops.py — niche_crop_detail(). */
export interface NicheCropDetailResponse {
  supported?: boolean;
  message_ar?: string;
  name_ar?: string;
  type_ar?: string;
  category_ar?: string;
  market_ar?: string;
  water_ar?: string;
  salinity_ar?: string;
  yemen_edge_ar?: string;
  uses_ar?: string;
  bonus_ar?: string;
  caution_ar?: string;
  disabled?: boolean;
}

/** api/crop_introduction.py — list_candidates(). */
export interface IntroductionCandidate {
  crop: string;
  name_ar?: string;
  type_ar?: string;
  zone?: string;
  product_ar?: string;
}
export interface IntroductionCandidatesResponse {
  zone_query?: string;
  candidates?: IntroductionCandidate[];
  note_ar?: string;
  disabled?: boolean;
}

export interface DisplayFact {
  label: string;
  value: string;
}

/** صفّ تفصيل مُسمّى — النصّ قيمة الخادم حرفيّاً، والتسمية عرضيّة فقط. */
export interface DetailRow {
  key: string;
  label: string;
  value: string;
}

const DASH = '—';
/** رماديّ محايد للقيم المجهولة — نفس محايد riskColor في approvalsConsole. */
const NEUTRAL = '#64748b';

// ── تنسيق (بلا حكم) ─────────────────────────────────────────────────────────

/** نصّ للعرض — null/غائب/فارغ ⇒ «—» (لا تلفيق). */
export function textOrDash(v: string | null | undefined): string {
  return v != null && v.trim() !== '' ? v : DASH;
}

// ── خرائط قيم معروفة (تلوين عرضيّ فقط — المجهول محايد، النصّ من الخادم) ─────

/** حالات api/chemical_safety.py: ok/blocked/warning — النصّ المعروض status_ar/
 *  message_ar من الخادم حرفيّاً؛ هنا اللون فقط. مجهول ⇒ محايد (لا اختراع حكم). */
const CHEMICAL_STATUS_COLORS: Record<string, string> = {
  ok: '#86efac',
  warning: '#fdba74',
  blocked: '#fca5a5',
};

export function chemicalStatusColor(status: string | null | undefined): string {
  if (!status) return NEUTRAL;
  return CHEMICAL_STATUS_COLORS[status.toLowerCase()] ?? NEUTRAL;
}

/** شدّة الحظر (CRITICAL/HIGH/MEDIUM) — نفس سلّم riskColor في approvalsConsole. */
const SEVERITY_COLORS: Record<string, string> = {
  critical: '#fca5a5',
  high: '#fdba74',
  medium: '#fde68a',
  low: '#86efac',
};

export function severityColor(severity: string | null | undefined): string {
  if (!severity) return NEUTRAL;
  return SEVERITY_COLORS[severity.toLowerCase()] ?? NEUTRAL;
}

// ── مشتقّات عرض من أشكال الخادم (الغائب يسقط، لا يُصفَّر) ──────────────────

/** رسالة الخادم لاستجابة غير مدعومة — تمرّ كما جاءت (supported=false ⇒ message_ar). */
export function serverUnsupportedMessage(
  resp: { supported?: boolean; message_ar?: string } | null | undefined,
): string | null {
  if (!resp || resp.supported !== false) return null;
  return resp.message_ar ?? null;
}

/** قيود التطبيق من فحص المادّة (حدّ/عازلة/إعادة دخول) — أرقام الخادم كما هي. */
export function chemicalLimitFacts(resp: ChemicalCheckResponse | null | undefined): DisplayFact[] {
  if (!resp) return [];
  const facts: DisplayFact[] = [];
  if (resp.max_kg_ha != null) facts.push({ label: 'الحدّ الأقصى', value: `${resp.max_kg_ha} كجم/هكتار` });
  if (resp.buffer_zone_m != null) facts.push({ label: 'المنطقة العازلة', value: `${resp.buffer_zone_m} م` });
  if (resp.reentry_hours != null) facts.push({ label: 'إعادة الدخول', value: `${resp.reentry_hours} ساعة` });
  return facts;
}

/** قائمة المحظورات كما يرتّبها الخادم — بلا مصفوفة ⇒ []. */
export function bannedRows(resp: BannedChemicalsResponse | null | undefined): BannedChemicalRow[] {
  if (!resp || !Array.isArray(resp.chemicals)) return [];
  return resp.chemicals;
}

/** محاصيل تقويم الزراعة كما يعيدها الخادم — بلا مصفوفة ⇒ []. */
export function plantingCropRows(resp: PlantingCropsResponse | null | undefined): PlantingCropRow[] {
  if (!resp || !Array.isArray(resp.crops)) return [];
  return resp.crops;
}

/** حقائق نافذة الزراعة — supported≠true ⇒ [] (message_ar عبر serverUnsupportedMessage). */
export function plantingWindowFacts(resp: PlantingWindowResponse | null | undefined): DisplayFact[] {
  if (!resp || resp.supported !== true) return [];
  const facts: DisplayFact[] = [];
  if (resp.season_ar) facts.push({ label: 'الموسم', value: resp.season_ar });
  if (resp.window_ar) facts.push({ label: 'النافذة', value: resp.window_ar });
  if (resp.optimal_ar) facts.push({ label: 'الأمثل', value: resp.optimal_ar });
  if (resp.harvest_ar) facts.push({ label: 'الحصاد', value: resp.harvest_ar });
  return facts;
}

/** الآفات المخزنيّة كما يعيدها الخادم — بلا مصفوفة ⇒ []. */
export function pestRows(resp: StoragePestsResponse | null | undefined): StoragePestRow[] {
  if (!resp || !Array.isArray(resp.pests)) return [];
  return resp.pests;
}

/** يبني صفوفاً مُسمّاة من حقول معروفة موجودة فقط — قيمة الخادم حرفيّاً. */
function presentRows(
  resp: Record<string, unknown>,
  labels: [key: string, label: string][],
): DetailRow[] {
  const rows: DetailRow[] = [];
  for (const [key, label] of labels) {
    const v = resp[key];
    if (typeof v === 'string' && v.trim() !== '') rows.push({ key, label, value: v });
  }
  return rows;
}

/** تسميات حقول تفصيل المحصول عالي القيمة (تختلف حسب الفئة — الموجود يُعرَض). */
const HIGH_VALUE_LABELS: [string, string][] = [
  ['type_ar', 'النوع'],
  ['value_ar', 'القيمة'],
  ['water_ar', 'الماء'],
  ['salinity_ar', 'الملوحة'],
  ['yield_ar', 'الإنتاج'],
  ['opportunity_ar', 'الفرصة'],
  ['evidence_ar', 'الدليل'],
  ['note_ar', 'ملاحظة'],
  ['fit_ar', 'الملاءمة'],
  ['reason_ar', 'السبب'],
];

/** صفوف تفصيل محصول عالي القيمة — supported≠true ⇒ [] (caution_ar يُعرَض منفصلاً). */
export function highValueDetailRows(resp: HighValueCropDetailResponse | null | undefined): DetailRow[] {
  if (!resp || resp.supported !== true) return [];
  return presentRows(resp as Record<string, unknown>, HIGH_VALUE_LABELS);
}

/** تسميات حقول تفصيل المنتج المتخصّص (niche_export_crops.py). */
const NICHE_LABELS: [string, string][] = [
  ['type_ar', 'النوع'],
  ['category_ar', 'الفئة'],
  ['market_ar', 'السوق'],
  ['water_ar', 'الماء'],
  ['salinity_ar', 'الملوحة'],
  ['yemen_edge_ar', 'الميزة اليمنيّة'],
  ['uses_ar', 'الاستخدامات'],
  ['bonus_ar', 'مزايا إضافيّة'],
];

/** صفوف تفصيل منتج متخصّص — supported≠true ⇒ [] (caution_ar يُعرَض منفصلاً). */
export function nicheDetailRows(resp: NicheCropDetailResponse | null | undefined): DetailRow[] {
  if (!resp || resp.supported !== true) return [];
  return presentRows(resp as Record<string, unknown>, NICHE_LABELS);
}

/** مرشّحو الإدخال كما يرشّحهم الخادم حسب المنطقة — بلا مصفوفة ⇒ []. */
export function introductionCandidates(
  resp: IntroductionCandidatesResponse | null | undefined,
): IntroductionCandidate[] {
  if (!resp || !Array.isArray(resp.candidates)) return [];
  return resp.candidates;
}

// ── خيارات إدخال ثابتة (مفاتيح API التي يعرفها الخادم — التسمية عرض فقط) ────

/** مناطق list_candidates في crop_introduction.py (all ⇒ بلا مُعامل zone). */
export const INTRODUCTION_ZONE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'all', label_ar: 'كلّ المناطق' },
  { key: 'tihama', label_ar: 'تهامة' },
  { key: 'jawf', label_ar: 'الجوف' },
  { key: 'highland', label_ar: 'المرتفعات' },
];
