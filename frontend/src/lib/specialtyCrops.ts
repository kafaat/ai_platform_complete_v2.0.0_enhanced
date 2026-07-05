// Specialty Crops & Traditional Timing — يعكس نقاط backend اليتيمة (P2) بلا قارئ واجهة:
//   /api/v1/high-value-crops/list      (routers/high_value_crops.py)
//   /api/v1/niche-crops/list           (routers/niche_crops.py)
//   /api/v1/aromatic-crops/list        (routers/aromatic_crops.py)
//   /api/v1/fodder-alternatives/list   (routers/fodder_alternatives.py)
//   /api/v1/introduction/card          (routers/introduction.py — crop_card)
//   /api/v1/introduction/field-fit     (routers/introduction.py — check_field_fit، POST مصادَق)
//   /api/v1/orchard/plan               (routers/orchard.py — mixed_orchard_plan)
//   /api/v1/orchard/economics          (routers/orchard.py — orchard_economics_note)
//   /api/v1/astronomical-timing/stars  (routers/astronomical_timing.py — get_calendar_stars)
//   /api/v1/astronomical-timing/cross-check (POST مصادَق — cross_check_with_gdd)
//   /api/v1/cultural-calendar          (routers/cultural_calendar.py — عرض فقط، خارج القرار)
//   /api/v1/regional-calendar          (routers/regional_calendar.py — حِميري/حضرمي)
//
// مكمّل لا مكرّر: CropSafetyKnowledgeCard يغطّي detail المحاصيل ومرشّحي الإدخال،
// وYemeniCalendarCard يغطّي أساس التقويم — هذه الشريحة للقوائم (list) وبطاقة
// الإدخال/فحص الملاءمة وتخطيط البستان والتوقيت الفلكي/الثقافي/الإقليمي.
//
// صدق صارم: النصوص والأحكام كلّها من الخادم (intro_ar/note_ar/caution_ar/
// disclaimer_ar/reason_ar/agreement_ar تمرّ حرفيّاً — لا إعادة حكم في الواجهة)؛
// null/غائب/فارغ ⇒ «—» أو يسقط (لا تصفير ولا تلفيق). خرائط الألوان هنا للتلوين
// العرضيّ فقط، والمجهول ⇒ محايد #64748b (نفس محايد riskColor في approvalsConsole).

// ── أشكال الاستجابة الحقيقيّة كما يعيدها الخادم ─────────────────────────────

/** api/high_value_crops.py — قيم crops لطبقتَي «مثبتة/بحذر» كائنات، ولطبقة «غير
 *  مناسبة» سلاسل نصّيّة (سبب)؛ لذا القيمة unknown ونُميّزها وقت التطبيع. */
export interface HighValueTierGroup {
  intro_ar?: string;
  crops?: Record<string, unknown>;
}
export interface HighValueCropsListResponse {
  proven_desert_ar?: HighValueTierGroup;
  conditional_ar?: HighValueTierGroup;
  not_suited_ar?: HighValueTierGroup;
  top_3_for_jawf_ar?: string[];
  principle_ar?: string;
  recommended_mix_ar?: string;
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** api/niche_export_crops.py — list_niche_crops() (بلا فئة ⇒ الشكل الكامل). */
export interface NicheCropsListResponse {
  crops?: Record<string, unknown>;
  count?: number;
  categories_ar?: string[];
  top_opportunities_ar?: string[];
  yemen_heritage_edge_ar?: string;
  principle_ar?: string;
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** api/aromatic_fodder_crops.py — list_aromatic_crops(). */
export interface AromaticCropsListResponse {
  crops?: Record<string, unknown>;
  count?: number;
  top_ar?: string[];
  principle_ar?: string;
  value_chain_ar?: string;
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** api/aromatic_fodder_crops.py — list_fodder_alternatives(). */
export interface FodderAlternativesListResponse {
  crops?: Record<string, unknown>;
  count?: number;
  problem_ar?: string;
  best_ar?: string;
  principle_ar?: string;
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** api/crop_introduction.py — crop_card(): supported=false ⇒ message_ar فقط. */
export interface IntroductionCardResponse {
  supported?: boolean;
  message_ar?: string;
  crop?: string;
  name_ar?: string;
  type_ar?: string;
  suitable_zone_ar?: string;
  requirements_ar?: { climate?: string; water?: string; soil?: string };
  season_ar?: string;
  product_ar?: string;
  inspiration_ar?: string;
  yemen_fit_ar?: string;
  caution_ar?: string;
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** جسم POST /api/v1/introduction/field-fit (api_models.py: FieldFitRequest). */
export interface FieldFitInput {
  crop: string;
  ph: number;
  ec_dsm: number;
  season_rain_mm?: number | null;
  temp_mean_c?: number | null;
  irrigated?: boolean;
}

/** api/crop_introduction.py — check_field_fit(): ثلاث حالات (غير مدعوم/بلا نطاقات
 *  كمّيّة/مُهدَّف). الحقول المُهدَّفة من crop_suitability.SuitabilityScore.to_dict. */
export interface FieldFitResponse {
  supported?: boolean;
  scored?: boolean;
  message_ar?: string;
  crop?: string;
  crop_ar?: string;
  name_ar?: string;
  score?: number; // 0-1 من الخادم
  rating_ar?: string; // ممتاز/جيّد/حدّي/غير مناسب — حكم الخادم
  reasons_ar?: string[];
  yemen_fit_ar?: string;
  caution_ar?: string;
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** api/orchard_planner.py — mixed_orchard_plan(): كتلة محصول في البستان المختلط. */
export interface OrchardBlock {
  crop_ar?: string;
  role_ar?: string;
  area_ha?: number;
  trees?: number;
  males_note_ar?: string;
  spacing_m?: string;
  first_yield_year?: number;
  full_yield_year?: number;
  water_ar?: string;
  risk_ar?: string; // منخفضة/متوسّطة/عالية
  note_ar?: string;
}
export interface OrchardTimelineEntry {
  year?: number;
  events_ar?: string[];
}
export interface OrchardPlanResponse {
  supported?: boolean;
  message_ar?: string;
  area_ha?: number;
  model_ar?: string;
  philosophy_ar?: string;
  blocks?: OrchardBlock[];
  total_trees?: number;
  cash_flow_timeline_ar?: OrchardTimelineEntry[];
  layout_advice_ar?: string;
  irrigation_ar?: string;
  arid_warning_ar?: string;
  strategy_ar?: string;
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** api/orchard_planner.py — orchard_economics_note(): نطاقات دولاريّة [أدنى، أقصى]. */
export interface OrchardIncomeStage {
  years?: string;
  usd_range?: number[];
  note_ar?: string;
}
export interface OrchardEconomicsResponse {
  supported?: boolean;
  message_ar?: string;
  area_ha?: number;
  establishment_usd_range?: number[];
  establishment_breakdown_ar?: Record<string, number[]>;
  annual_income_stages_ar?: OrchardIncomeStage[];
  high_risks_ar?: string[];
  disclaimer_ar?: string;
  disabled?: boolean;
}

/** api/astronomical_timing.py — StarTiming.to_dict(). */
export interface CalendarStar {
  name_ar?: string;
  heliacal_rising_approx?: string;
  season_marker_ar?: string;
  agricultural_note_ar?: string;
}
export interface CalendarStarsResponse {
  purpose_ar?: string;
  is_observational?: boolean;
  is_astrological?: boolean;
  disclaimer_ar?: string;
  stars?: CalendarStar[];
  disabled?: boolean;
}

/** جسم POST /api/v1/astronomical-timing/cross-check (AstronomicalCrossCheckRequest). */
export interface CrossCheckInput {
  current_date: string; // YYYY-MM-DD
  gdd_stage?: string | null;
  anchor?: string; // suhail_rising افتراضاً
}

/** api/astronomical_timing.py — TimingCrossCheck.to_dict() أو {error_ar}. */
export interface CrossCheckResponse {
  error_ar?: string;
  star_anchor_ar?: string;
  days_from_anchor?: number;
  gdd_stage?: string | null;
  agreement_ar?: string;
  disabled?: boolean;
}

/** api/cultural_calendar.py — CulturalNote.to_dict() ضمن الردّ. */
export interface CulturalNote {
  name_ar?: string;
  period_ar?: string;
  traditional_practice_ar?: string;
}
export interface CulturalCalendarResponse {
  display_only?: boolean;
  used_in_decision_engine?: boolean;
  disclaimer_ar?: string;
  notes?: CulturalNote[];
  disabled?: boolean;
}

/** api/astronomical_timing.py — get_regional_calendar(): matched=false ⇒ رسالة+المتاح. */
export interface RegionalCalendarEntry {
  period_name_ar?: string;
  approx_gregorian_ar?: string;
  agricultural_meaning_ar?: string;
}
export interface RegionalCalendarResponse {
  is_observational?: boolean;
  is_astrological?: boolean;
  disclaimer_ar?: string;
  regional_note_ar?: string;
  matched?: boolean;
  message_ar?: string;
  available?: string[];
  calendar_key?: string;
  name_ar?: string;
  structure_ar?: string;
  region_ar?: string;
  entries?: RegionalCalendarEntry[];
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

/** محصول مُطبَّع من خريطة الخادم — الاسم مفتاح الخريطة، والصفوف/التحذير من قيمته. */
export interface CropEntry {
  name: string;
  rows: DetailRow[];
  /** caution_ar مُستخرَج للتلوين التحذيري المنفصل (لا يُكرَّر في الصفوف). */
  caution_ar: string | null;
  /** قيمة نصّيّة مباشرة (طبقة «غير مناسبة» في high-value قيمها سبب نصّيّ لا كائن). */
  reason_ar: string | null;
}

const DASH = '—';
/** رماديّ محايد للقيم المجهولة — نفس محايد riskColor في approvalsConsole. */
const NEUTRAL = '#64748b';

// ── تنسيق (بلا حكم) ─────────────────────────────────────────────────────────

/** نصّ للعرض — null/غائب/فارغ ⇒ «—» (لا تلفيق). */
export function textOrDash(v: string | null | undefined): string {
  return v != null && v.trim() !== '' ? v : DASH;
}

/** نصّ موجود أو null (لا «—») — للحقول التي تسقط كلّيّاً حين تغيب. */
function textPresent(v: string | null | undefined): string | null {
  return typeof v === 'string' && v.trim() !== '' ? v : null;
}

/** نطاق دولاريّ [أدنى، أقصى] ⇒ «أدنى–أقصى $»؛ غير صالح ⇒ «—» (أرقام الخادم كما هي). */
export function usdRange(range: number[] | null | undefined): string {
  if (!Array.isArray(range) || range.length < 2) return DASH;
  const [lo, hi] = range;
  if (typeof lo !== 'number' || !Number.isFinite(lo) || typeof hi !== 'number' || !Number.isFinite(hi)) {
    return DASH;
  }
  return `${lo}–${hi} $`;
}

// ── خرائط قيم معروفة (تلوين عرضيّ فقط — المجهول محايد، النصّ من الخادم) ─────

/** تقييم ملاءمة الحقل (crop_suitability): ممتاز→حدّي→غير مناسب. النصّ المعروض
 *  rating_ar من الخادم حرفيّاً؛ هنا اللون فقط. مجهول/غائب ⇒ محايد (لا اختراع حكم). */
const RATING_COLORS: Record<string, string> = {
  'ممتاز': '#4ade80',
  'جيّد': '#86efac',
  'حدّي': '#fdba74',
  'غير مناسب': '#fca5a5',
};
export function ratingColor(rating: string | null | undefined): string {
  if (!rating) return NEUTRAL;
  return RATING_COLORS[rating.trim()] ?? NEUTRAL;
}

/** مخاطرة كتلة البستان (orchard_planner: risk_ar) — منخفضة/متوسّطة/عالية. اللون
 *  فقط؛ النصّ من الخادم. مجهول ⇒ محايد. */
const RISK_COLORS: Record<string, string> = {
  'منخفضة': '#86efac',
  'متوسّطة': '#fdba74',
  'عالية': '#fca5a5',
};
export function riskColorAr(risk: string | null | undefined): string {
  if (!risk) return NEUTRAL;
  return RISK_COLORS[risk.trim()] ?? NEUTRAL;
}

// ── تطبيع خرائط المحاصيل (crops: {اسم: كائن|نصّ}) ──────────────────────────

/** يبني صفوفاً مُسمّاة من حقول معروفة موجودة فقط — قيمة الخادم حرفيّاً. */
function presentRows(
  obj: Record<string, unknown>,
  labels: [key: string, label: string][],
): DetailRow[] {
  const rows: DetailRow[] = [];
  for (const [key, label] of labels) {
    const v = obj[key];
    if (typeof v === 'string' && v.trim() !== '') rows.push({ key, label, value: v });
  }
  return rows;
}

/** يطبّع خريطة الخادم {اسم: كائن|نصّ} إلى قائمة محاصيل عرضيّة:
 *  القيمة الكائن ⇒ صفوف من التسميات + caution_ar منفصلاً؛ القيمة النصّ ⇒ reason_ar
 *  (طبقة «غير مناسبة» في high-value). خريطة غائبة/غير كائن ⇒ [] بصدق. */
export function cropEntries(
  crops: Record<string, unknown> | null | undefined,
  labels: [string, string][],
): CropEntry[] {
  if (!crops || typeof crops !== 'object') return [];
  const out: CropEntry[] = [];
  for (const [name, val] of Object.entries(crops)) {
    if (typeof val === 'string') {
      out.push({ name, rows: [], caution_ar: null, reason_ar: textPresent(val) });
    } else if (val && typeof val === 'object') {
      const obj = val as Record<string, unknown>;
      out.push({
        name,
        rows: presentRows(obj, labels),
        caution_ar: textPresent(obj.caution_ar as string | undefined),
        reason_ar: null,
      });
    }
  }
  return out;
}

// تسميات حقول المحاصيل (مفاتيح API التي يعرفها الخادم — التسمية عرض فقط).
// مجموعة عليا لـhigh-value تغطّي طبقتَي «مثبتة» (yield/opportunity/evidence) و«بحذر»
// (note/fit) معاً؛ presentRows يلتقط الموجود فقط فيصلح الاثنين.
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
];
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
const AROMATIC_LABELS: [string, string][] = [
  ['type_ar', 'النوع'],
  ['product_ar', 'المنتج'],
  ['water_ar', 'الماء'],
  ['value_ar', 'القيمة'],
  ['yemen_fit_ar', 'الملاءمة اليمنيّة'],
];
const FODDER_LABELS: [string, string][] = [
  ['type_ar', 'النوع'],
  ['advantage_ar', 'الميزة'],
  ['water_ar', 'الماء'],
  ['evidence_ar', 'الدليل'],
  ['yemen_fit_ar', 'الملاءمة اليمنيّة'],
];

/** طبقة من قائمة المحاصيل عالية القيمة — مقدّمتها ومحاصيلها المُطبَّعة. */
export interface HighValueTier {
  key: 'proven' | 'conditional' | 'not_suited';
  intro_ar: string | null;
  entries: CropEntry[];
}

/** يستخرج الطبقات الثلاث بترتيب الصدق (مثبتة → بحذر → غير مناسبة). الطبقة الغائبة
 *  تسقط؛ طبقة «غير مناسبة» قيمها نصّيّة فتظهر كـreason_ar (cropEntries يميّزها). */
export function highValueTiers(resp: HighValueCropsListResponse | null | undefined): HighValueTier[] {
  if (!resp) return [];
  const groups: [HighValueTier['key'], HighValueTierGroup | undefined][] = [
    ['proven', resp.proven_desert_ar],
    ['conditional', resp.conditional_ar],
    ['not_suited', resp.not_suited_ar],
  ];
  const tiers: HighValueTier[] = [];
  for (const [key, g] of groups) {
    if (!g) continue;
    tiers.push({
      key,
      intro_ar: textPresent(g.intro_ar),
      entries: cropEntries(g.crops, HIGH_VALUE_LABELS),
    });
  }
  return tiers;
}

/** محاصيل قائمة المنتجات المتخصّصة — بلا خريطة ⇒ []. */
export function nicheEntries(resp: NicheCropsListResponse | null | undefined): CropEntry[] {
  return cropEntries(resp?.crops, NICHE_LABELS);
}

/** محاصيل قائمة النباتات العطريّة — بلا خريطة ⇒ []. */
export function aromaticEntries(resp: AromaticCropsListResponse | null | undefined): CropEntry[] {
  return cropEntries(resp?.crops, AROMATIC_LABELS);
}

/** بدائل الأعلاف — بلا خريطة ⇒ []. */
export function fodderEntries(resp: FodderAlternativesListResponse | null | undefined): CropEntry[] {
  return cropEntries(resp?.crops, FODDER_LABELS);
}

// ── مشتقّات عرض من بقيّة الأشكال ─────────────────────────────────────────────

/** رسالة الخادم لاستجابة غير مدعومة — تمرّ كما جاءت (supported=false ⇒ message_ar). */
export function serverUnsupportedMessage(
  resp: { supported?: boolean; message_ar?: string } | null | undefined,
): string | null {
  if (!resp || resp.supported !== false) return null;
  return textPresent(resp.message_ar);
}

/** متطلّبات بطاقة الإدخال (climate/water/soil) — الموجود فقط، قيمة الخادم حرفيّاً. */
export function introductionRequirementRows(resp: IntroductionCardResponse | null | undefined): DetailRow[] {
  if (!resp || resp.supported !== true || !resp.requirements_ar) return [];
  return presentRows(resp.requirements_ar as Record<string, unknown>, [
    ['climate', 'المناخ'],
    ['water', 'الماء'],
    ['soil', 'التربة'],
  ]);
}

/** حقائق فحص الملاءمة الكمّي — scored=true فقط (score كسر الخادم يُعرَض ٪، rating_ar
 *  حكم الخادم حرفيّاً). غير مُهدَّف ⇒ [] (message_ar يُعرَض منفصلاً في الواجهة). */
export function fieldFitFacts(resp: FieldFitResponse | null | undefined): DisplayFact[] {
  if (!resp || resp.scored !== true) return [];
  const facts: DisplayFact[] = [];
  if (typeof resp.score === 'number' && Number.isFinite(resp.score)) {
    facts.push({ label: 'الدرجة', value: `${Math.round(resp.score * 100)}٪` });
  }
  if (textPresent(resp.rating_ar)) facts.push({ label: 'التقييم', value: resp.rating_ar as string });
  return facts;
}

/** كتل البستان كما يرتّبها الخادم — supported≠true/بلا مصفوفة ⇒ []. */
export function orchardBlocks(resp: OrchardPlanResponse | null | undefined): OrchardBlock[] {
  if (!resp || resp.supported !== true || !Array.isArray(resp.blocks)) return [];
  return resp.blocks;
}

/** جدول التدفّق النقدي الزمني — بلا مصفوفة ⇒ []. */
export function orchardTimeline(resp: OrchardPlanResponse | null | undefined): OrchardTimelineEntry[] {
  if (!resp || resp.supported !== true || !Array.isArray(resp.cash_flow_timeline_ar)) return [];
  return resp.cash_flow_timeline_ar;
}

/** مراحل الدخل السنويّ التقديريّة — supported≠true/بلا مصفوفة ⇒ []. */
export function economicsStages(resp: OrchardEconomicsResponse | null | undefined): OrchardIncomeStage[] {
  if (!resp || resp.supported !== true || !Array.isArray(resp.annual_income_stages_ar)) return [];
  return resp.annual_income_stages_ar;
}

/** نجوم التقويم كما يعيدها الخادم — بلا مصفوفة ⇒ []. */
export function calendarStars(resp: CalendarStarsResponse | null | undefined): CalendarStar[] {
  if (!resp || !Array.isArray(resp.stars)) return [];
  return resp.stars;
}

/** ملاحظات التقويم الثقافي — بلا مصفوفة ⇒ []. */
export function culturalNotes(resp: CulturalCalendarResponse | null | undefined): CulturalNote[] {
  if (!resp || !Array.isArray(resp.notes)) return [];
  return resp.notes;
}

/** مداخل التقويم الإقليمي — matched≠true/بلا مصفوفة ⇒ []. */
export function regionalEntries(resp: RegionalCalendarResponse | null | undefined): RegionalCalendarEntry[] {
  if (!resp || resp.matched !== true || !Array.isArray(resp.entries)) return [];
  return resp.entries;
}

// ── خيارات إدخال ثابتة (مفاتيح API التي يعرفها الخادم — التسمية عرض فقط) ────

/** مناطق crop_introduction.py المطابقة لـ_ALIASES (all ⇒ بلا مُعامل). */
export const INTRODUCTION_ZONE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'tihama', label_ar: 'تهامة' },
  { key: 'jawf', label_ar: 'الجوف' },
  { key: 'highland', label_ar: 'المرتفعات' },
];

/** محافظات _GOVERNORATE_CALENDAR في astronomical_timing.py — المفتاح API، التسمية عرض.
 *  فارغ ⇒ لا مُعامل (الخادم يعيد matched=false مع المتاح). */
export const REGIONAL_GOVERNORATE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'sanaa', label_ar: 'صنعاء (الهضبة)' },
  { key: 'dhamar', label_ar: 'ذمار (الهضبة)' },
  { key: 'al_bayda', label_ar: 'البيضاء (الهضبة)' },
  { key: 'ibb', label_ar: 'إبّ (الهضبة)' },
  { key: 'al_jawf', label_ar: 'الجوف (الهضبة)' },
  { key: 'hadramout', label_ar: 'حضرموت (الوادي)' },
  { key: 'shabwa', label_ar: 'شبوة (الوادي)' },
  { key: 'al_mahra', label_ar: 'المهرة (الوادي)' },
];

/** مراسٍ فلكيّة يعرفها cross_check_with_gdd (_SEASON_ANCHORS + ترجمة anchor_ar). */
export const ASTRONOMICAL_ANCHOR_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'suhail_rising', label_ar: 'شروق سهيل (~24 أغسطس)' },
  { key: 'autumn_equinox', label_ar: 'الاعتدال الخريفي' },
  { key: 'spring_equinox', label_ar: 'الاعتدال الربيعي' },
];
