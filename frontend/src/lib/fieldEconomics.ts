// FieldView Farm Business Layer — مستوحى من Granular/Farmbrite/FarmLogs: يربط القرار
// الزراعيّ بالتكلفة والربحيّة لكلّ حقل/موسم. لا مصدر تكاليف ملفَّق — الأرقام يُدخِلها
// المستخدم (ريّ/عمالة/مدخلات/أخرى) و/أو تُشتقّ لاحقاً من سجلّ الريّ (irrigation_runs)
// عند ربطه. المحرّك هنا حسابيّ نقيّ صادق: يجمع المُدخَل، ويحسب /هكتار والإيراد والصافي
// فقط حين تتوفّر مدخلاتها؛ وإلّا يُرجِع null بدل رقم مُختلَق.
export interface FieldCostInputs {
  areaHa?: number | null;
  irrigationCost?: number | null;
  laborCost?: number | null;
  inputsCost?: number | null;
  otherCost?: number | null;
  /** إنتاج متوقَّع/فعليّ طن/هكتار (اختياريّ — للإيراد). */
  yieldTPerHa?: number | null;
  /** سعر البيع لكلّ طن (اختياريّ — للإيراد). */
  pricePerT?: number | null;
  currency?: string;
}

export interface FieldEconomicsBreakdownItem {
  label: string;
  value: number;
}

export interface FieldEconomics {
  currency: string;
  /** إجماليّ التكلفة المُدخَلة (مجموع البنود المتاحة). */
  totalCost: number;
  /** هل أُدخِل أيّ بند تكلفة؟ (لتمييز 0 الحقيقيّ عن غياب الإدخال). */
  hasAnyCost: boolean;
  costPerHa: number | null;
  revenue: number | null;
  netProfit: number | null;
  marginPct: number | null;
  breakdown: FieldEconomicsBreakdownItem[];
}

function num(v: number | null | undefined): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** حجم الماء المُطبَّق م³ من عمق الريّ (مم) × المساحة (هـ). 1 مم على 1 هكتار = 10 م³.
 *  المصدر الحقيقيّ: irrigation_mm_total من دفتر مياه الحقل (water-efficiency). null عند نقص المدخلات. */
export function irrigationVolumeM3(irrigationMm: number | null | undefined, areaHa: number | null | undefined): number | null {
  const mm = num(irrigationMm);
  const area = num(areaHa);
  if (mm == null || mm < 0 || area == null || area <= 0) return null;
  return mm * area * 10;
}

/** تكلفة الريّ المقدَّرة = حجم الماء الحقيقيّ × سعر المتر المكعّب (يُدخِله المستخدم). null عند نقص أيٍّ منهما. */
export function estimateIrrigationCost(
  irrigationMm: number | null | undefined,
  areaHa: number | null | undefined,
  pricePerM3: number | null | undefined,
): number | null {
  const vol = irrigationVolumeM3(irrigationMm, areaHa);
  const price = num(pricePerM3);
  if (vol == null || price == null || price < 0) return null;
  return vol * price;
}

export function computeFieldEconomics(input: FieldCostInputs): FieldEconomics {
  const currency = input.currency || 'ر.ي';
  const items: FieldEconomicsBreakdownItem[] = [];
  const push = (label: string, v: number | null) => { if (v != null) items.push({ label, value: v }); };
  push('الريّ', num(input.irrigationCost));
  push('العمالة', num(input.laborCost));
  push('المدخلات', num(input.inputsCost));
  push('أخرى', num(input.otherCost));

  const hasAnyCost = items.length > 0;
  const totalCost = items.reduce((s, i) => s + i.value, 0);

  const area = num(input.areaHa);
  const costPerHa = hasAnyCost && area != null && area > 0 ? totalCost / area : null;

  const yieldTPerHa = num(input.yieldTPerHa);
  const pricePerT = num(input.pricePerT);
  const revenue =
    yieldTPerHa != null && pricePerT != null && area != null && area > 0
      ? yieldTPerHa * area * pricePerT
      : null;

  const netProfit = revenue != null && hasAnyCost ? revenue - totalCost : null;
  const marginPct = netProfit != null && revenue != null && revenue > 0 ? (netProfit / revenue) * 100 : null;

  return { currency, totalCost, hasAnyCost, costPerHa, revenue, netProfit, marginPct, breakdown: items };
}
