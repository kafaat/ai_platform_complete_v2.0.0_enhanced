// FieldView Crop Card — يعكس «بطاقة المحصول/الصنف» المرجعيّة المُخزَّنة في backend
// (/api/v1/crop-cards — YAML مُتحقَّق: FAO-56 Kc · Maas-Hoffman ملوحة · GDD · حاكمات)
// على الحقل النشط. صدق: معرفة مرجعيّة محايدة الموقع لا معايرة/إنتاج (note_ar من
// الخادم تُعرَض)، الحقول الغائبة null وتُعرَض «—»، ومطابقة المحصول بالاسم صريحة
// (لا تخمين عند الالتباس ⇒ null وحالة «لا بطاقة»).

export interface CropIndexEntry {
  crop_id: string;
  name_ar?: string | null;
  name_en?: string | null;
  crop_family?: string | null;
  varieties?: string[];
}

export interface CropCardsIndex {
  total_crops: number;
  total_varieties: number;
  crops: CropIndexEntry[];
  note_ar?: string;
}

/** بطاقة المحصول كما تأتي من YAML (نلتقط ما نعرضه فقط — بنية مرنة). */
export interface CropCardDoc {
  crop_id?: string;
  name_ar?: string | null;
  name_en?: string | null;
  crop_family?: string | null;
  kc?: { initial?: number; mid?: number; end?: number; stage_days?: number[] };
  salinity?: { threshold_ece_ds_m?: number; slope_pct_per_ds_m?: number };
  thermal?: { gdd_base_c?: number; gdd_to_maturity?: number; flowering_safe_max_c?: number };
  governing?: { ph?: { min?: number; max?: number }; ece_ds_m?: { min?: number; max?: number } };
  modifying?: {
    nitrogen_kg_ha_required?: number;
    phosphorus_kg_ha_required?: number;
    potassium_kg_ha_required?: number;
  };
  pest_susceptibility?: { pests?: string[] };
  phenology?: { total_cycle_days?: number };
}

export interface CropCardResponse {
  card: CropCardDoc;
  varieties: string[];
}

export interface VarietyDiseaseWatch {
  variety_id: string;
  resistant_ar: string[];
  note_ar?: string;
}

export interface VarietyExpectedHarvest {
  variety_id: string;
  sowing_date: string;
  days_to_maturity: number | null;
  expected_harvest_date: string | null;
  expected_flowering_date: string | null;
}

export interface VarietySalinity {
  variety_id: string;
  threshold_ece_ds_m: number | null;
  measured_ece_ds_m: number;
  class: string | null;
  expected_yield_loss_pct: number | null;
  note_ar?: string;
}

function norm(s: string | null | undefined): string {
  return (s ?? '')
    .trim()
    .toLowerCase()
    // تطبيع عربيّ خفيف: إزالة «ال» التعريف والتشكيل لمطابقة أوسع دون تخمين.
    .replace(/[ً-ْ]/g, '')
    .replace(/^ال/, '');
}

/** يطابق تسمية محصول الحقل (عربيّ/إنجليزيّ/معرّف) مع فهرس البطاقات؛ null إن لم يُوجَد. */
export function matchCropId(cropLabel: string | null | undefined, crops: CropIndexEntry[] | null | undefined): string | null {
  const label = norm(cropLabel);
  if (!label || !Array.isArray(crops)) return null;
  for (const c of crops) {
    if (norm(c.name_ar) === label || norm(c.name_en) === label || norm(c.crop_id) === label) return c.crop_id;
  }
  // مطابقة احتواء حذرة (تسميات مثل «قمح بلديّ») — فقط حين تكون النتيجة وحيدة.
  const partial = crops.filter((c) => {
    const ar = norm(c.name_ar);
    const en = norm(c.name_en);
    return (ar && label.includes(ar)) || (en && label.includes(en));
  });
  return partial.length === 1 ? partial[0].crop_id : null;
}

export interface CropCardFact {
  label: string;
  value: string;
}

/** يستخرج حقائق العرض من البطاقة — حقيقيّة فقط، الغائب يُسقَط لا يُختلَق. */
export function summarizeCropCard(card: CropCardDoc | null | undefined): CropCardFact[] {
  if (!card) return [];
  const facts: CropCardFact[] = [];
  const kc = card.kc;
  if (kc && [kc.initial, kc.mid, kc.end].every((v) => typeof v === 'number')) {
    facts.push({ label: 'Kc (بدء/وسط/نهاية)', value: `${kc.initial} / ${kc.mid} / ${kc.end}` });
  }
  const cycle = card.phenology?.total_cycle_days;
  if (typeof cycle === 'number' && cycle > 0) facts.push({ label: 'دورة النموّ', value: `${cycle} يوماً` });
  const gdd = card.thermal?.gdd_to_maturity;
  if (typeof gdd === 'number' && gdd > 0) {
    const base = card.thermal?.gdd_base_c;
    facts.push({ label: 'GDD للنضج', value: `${gdd}${typeof base === 'number' ? ` (أساس ${base}°م)` : ''}` });
  }
  const heat = card.thermal?.flowering_safe_max_c;
  if (typeof heat === 'number') facts.push({ label: 'حدّ حرارة التزهير', value: `${heat}°م` });
  const sal = card.salinity?.threshold_ece_ds_m;
  if (typeof sal === 'number') {
    const slope = card.salinity?.slope_pct_per_ds_m;
    facts.push({
      label: 'عتبة الملوحة ECe',
      value: `${sal} dS/m${typeof slope === 'number' ? ` (−${slope}٪/وحدة)` : ''}`,
    });
  }
  const ph = card.governing?.ph;
  if (ph && typeof ph.min === 'number' && typeof ph.max === 'number') {
    facts.push({ label: 'pH', value: `${ph.min}–${ph.max}` });
  }
  const m = card.modifying;
  const npk = [m?.nitrogen_kg_ha_required, m?.phosphorus_kg_ha_required, m?.potassium_kg_ha_required];
  if (npk.every((v) => typeof v === 'number')) {
    facts.push({ label: 'N-P-K (كغ/هـ)', value: npk.join('-') });
  }
  const pests = card.pest_susceptibility?.pests;
  if (Array.isArray(pests) && pests.length > 0) facts.push({ label: 'آفات مرصودة', value: String(pests.length) });
  return facts;
}
