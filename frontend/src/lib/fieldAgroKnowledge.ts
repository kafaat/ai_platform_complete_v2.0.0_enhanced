// FieldView Agro-Knowledge — يعكس طبقة المعرفة الزراعيّة الخلفيّة التي لا قارئ لها
// في الواجهة بعد: الإكثار (/api/v1/propagation/crop) · ما بعد الحصاد
// (/api/v1/postharvest/best-practices) · دليل/أصناف/آفات البنّ اليمني
// (/api/v1/coffee/{guide,varieties,pests}). كلّها معرفة مرجعيّة نقيّة من مصادر
// موثّقة (Wikifarmer/جامعات، FAO، تراث يمني) — لا معايرة/إنتاج لموقع.
//
// صدق العرض: نصّ الخادم يمرّ كما هو (لا إعادة صياغة/حكم) · القيمة الغائبة null
// تُعرَض «—» · الحقل المفقود يُسقَط لا يُختلَق · حقول المنشأ (note_ar / source_ar /
// disclaimer_ar وأخواتها) تُصان وتُعرَض لأنّ منشأ المعرفة جوهريّ في الإرشاد.
// مطابقة محصول البنّ بالاسم صريحة (لا تخمين) — تُفعِّل بطاقات البنّ فقط للبنّ.

export const DASH = '—';

/** null/undefined ⇒ «—»؛ خلاف ذلك يمرّ نصّ الخادم كما هو (بعد تشذيب فراغ فقط). */
export function orDash(s: string | number | null | undefined): string {
  if (s === null || s === undefined) return DASH;
  const t = String(s).trim();
  return t === '' ? DASH : t;
}

// ── الأشكال الحقيقيّة (مطابقة لـ return {...} في core advisors) ──────────────

/** GET /api/v1/propagation/crop?crop= — طريقة الإكثار المناسبة لمحصول/شجرة. */
export interface CropPropagation {
  supported: boolean;
  message_ar?: string;        // عند supported=false: قائمة المتاح
  crop?: string;
  recommended_method?: string;
  method_name_ar?: string;
  why_ar?: string;
  method_tip_ar?: string;
  disclaimer_ar?: string;
}

/** GET /api/v1/postharvest/best-practices?crop= — ممارسات تخزين تقلّل الفقد. */
export interface PostharvestPractice {
  topic_ar: string;
  detail_ar: string;
}
export interface PostharvestBestPractices {
  practices_ar: PostharvestPractice[];
  principle_ar?: string;
  yemen_context_ar?: string;
  chemical_note_ar?: string;
  disclaimer_ar?: string;
  crop_moisture_ar?: string;  // يُضاف فقط حين يُمرّر محصول مدعوم
}

/** GET /api/v1/coffee/guide — دليل زراعة البنّ اليمني (البنّ فقط). */
export interface CoffeePractice {
  topic_ar: string;
  detail_ar: string;
}
export interface CoffeeGuide {
  crop_ar?: string;
  type_ar?: string;
  practices_ar: CoffeePractice[];
  quality_factors_ar?: string[];
  economic_note_ar?: string;
  disclaimer_ar?: string;
}

/** GET /api/v1/coffee/varieties — أصناف البنّ اليمنيّة. */
export interface CoffeeVariety {
  name_ar: string;
  region_ar: string;
  note_ar?: string;
}
export interface CoffeeVarieties {
  varieties: CoffeeVariety[];
  note_ar?: string;
  region_query?: string;
}

/** GET /api/v1/coffee/pests — آفات البنّ الرئيسيّة (مرتبطة بـIPM). */
export interface CoffeePest {
  name_ar: string;
  scientific?: string;
  note_ar?: string;
}
export interface CoffeePests {
  pests_ar: CoffeePest[];
  ipm_note_ar?: string;
}

export interface KnowledgeFact {
  label: string;
  value: string;
}

// ── مطابقة محصول البنّ بالاسم (صريحة — لا تخمين) ──────────────────────────────
function norm(s: string | null | undefined): string {
  return (s ?? '')
    .trim()
    .toLowerCase()
    // تطبيع عربيّ خفيف: إزالة التشكيل و«ال» التعريف لمطابقة أوسع دون تخمين.
    .replace(/[ً-ْ]/g, '')
    .replace(/^ال/, '');
}

// أسماء البنّ العربيّة/الإنجليزيّة المعروفة — لا مطابقة احتواء فضفاضة.
const COFFEE_LABELS = new Set(['بن', 'بنّ', 'قهوة', 'coffee', 'arabica', 'coffea']);

/** هل محصول الحقل بُنّ؟ يفعّل بطاقات البنّ فقط عند تطابق صريح (لا تخمين عند الالتباس). */
export function isCoffeeCrop(cropLabel: string | null | undefined): boolean {
  const label = norm(cropLabel);
  if (!label) return false;
  if (COFFEE_LABELS.has(label)) return true;
  // «بنّ يمني»/«coffea arabica»: تطابق كلمة كاملة داخل التسمية.
  const words = label.split(/[\s/()-]+/).filter(Boolean);
  return words.some((w) => COFFEE_LABELS.has(w));
}

// ── محوّلات العرض النقيّة (الغائب يُسقَط لا يُختلَق) ─────────────────────────────

/** حقائق إكثار المحصول للعرض — حقيقيّة فقط، النصّ يمرّ كما هو من الخادم. */
export function propagationFacts(data: CropPropagation | null | undefined): KnowledgeFact[] {
  if (!data || !data.supported) return [];
  const facts: KnowledgeFact[] = [];
  if (data.method_name_ar) facts.push({ label: 'الطريقة المُوصى بها', value: data.method_name_ar });
  if (data.why_ar) facts.push({ label: 'لماذا', value: data.why_ar });
  if (data.method_tip_ar) facts.push({ label: 'نصيحة', value: data.method_tip_ar });
  return facts;
}

/**
 * يجمع حقول المنشأ/التنويه الموجودة فعلاً في كائن معرفة (note_ar/source_ar/
 * disclaimer_ar + سياق يمني/اقتصادي/كيميائي/مبدأ/IPM). الغائب يُسقَط — لا يُختلَق.
 * منشأ المعرفة جوهريّ: يُعرَض دائماً حين يزوّده الخادم.
 */
export function provenanceNotes(obj: Record<string, unknown> | null | undefined): string[] {
  if (!obj) return [];
  const keys = [
    'note_ar', 'source_ar', 'principle_ar', 'ipm_note_ar',
    'yemen_context_ar', 'economic_note_ar', 'chemical_note_ar', 'disclaimer_ar',
  ] as const;
  const out: string[] = [];
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === 'string' && v.trim() !== '') out.push(v.trim());
  }
  return out;
}

/** صفوف أصناف البنّ للعرض — يُبقي note_ar لكلّ صنف (يُعرَض «—» إن غاب). */
export function coffeeVarietyRows(data: CoffeeVarieties | null | undefined): { name: string; region: string; note: string }[] {
  const list = data?.varieties;
  if (!Array.isArray(list)) return [];
  return list.map((v) => ({
    name: orDash(v.name_ar),
    region: orDash(v.region_ar),
    note: orDash(v.note_ar),
  }));
}

/** صفوف آفات البنّ للعرض — يُبقي الاسم العلميّ وnote_ar (الغائب «—»). */
export function coffeePestRows(data: CoffeePests | null | undefined): { name: string; scientific: string; note: string }[] {
  const list = data?.pests_ar;
  if (!Array.isArray(list)) return [];
  return list.map((p) => ({
    name: orDash(p.name_ar),
    scientific: orDash(p.scientific),
    note: orDash(p.note_ar),
  }));
}

/** ممارسات (تخزين/زراعة البنّ) موحّدة للعرض — يُسقِط أيّ صفّ بلا topic/detail. */
export function practiceRows(
  practices: { topic_ar?: string | null; detail_ar?: string | null }[] | null | undefined,
): { topic: string; detail: string }[] {
  if (!Array.isArray(practices)) return [];
  return practices
    .filter((p) => (p?.topic_ar ?? '').trim() !== '' || (p?.detail_ar ?? '').trim() !== '')
    .map((p) => ({ topic: orDash(p.topic_ar), detail: orDash(p.detail_ar) }));
}
