// FieldView Profitability — يعكس سجلّ التكاليف/الربحيّة الفعليّ المُخزَّن (farm_operations_ledger,
// v100–v102) في الواجهة. صدق صارم: يقرأ أرقاماً حقيقيّة من النقاط الخلفيّة فقط؛ الحقول الغائبة
// (null) تبقى غير معروفة «—» ولا تُملأ بصفر مُلفَّق؛ والميزة قد تكون مُعطَّلة (404) أو القاعدة
// غير مفعّلة (note_ar) فتُعرَض حالة صادقة بدل رقم مُختلَق.

/** ملخّص رقابي من /api/v1/farm-ledger/summary (summary=null عند التعطّل). */
export interface LedgerSummary {
  operation_count: number;
  total_cost: number;
  direct_cost: number;
  indirect_cost: number;
  cost_breakdown: Record<string, number>;
  water_volume_m3: number;
  energy_kwh: number;
  diesel_liters: number;
  equipment_hours: number;
  labor_hours: number;
  syncable_cost: number;
  control_only: boolean;
}

export interface LedgerSummaryResponse {
  summary: LedgerSummary | null;
  note_ar?: string;
  /** يُضاف من الخطّاف عند 404 (الميزة مُعطَّلة) — لا يأتي من الخادم. */
  disabled?: boolean;
}

/** ربحيّة الموسم من /api/v1/farm-ledger/profitability/{season_id}. */
export interface ProfitabilitySummary {
  season_id: string;
  revenue: number;
  total_cost: number;
  gross_margin: number;
  margin_percent: number | null;
  yield_quantity: number | null;
  unit: string | null;
  cost_per_unit: number | null;
  revenue_per_unit: number | null;
  currency: string;
}

export interface ProfitabilityResponse {
  season_id: string;
  profitability: ProfitabilitySummary | null;
  note_ar?: string;
  disabled?: boolean;
}

/** بند انحراف من /api/v1/farm-ledger/variance/{season_id}. */
export interface VarianceLine {
  season_id: string;
  category: string;
  stage: string;
  planned_cost: number;
  actual_cost: number;
  variance_amount: number;
  variance_percent: number | null;
  severity: string;
  explanation: string;
}

export interface CostRecommendation {
  code: string;
  title_ar: string;
  message_ar: string;
  severity: string;
}

export interface VarianceResponse {
  season_id: string;
  variance: VarianceLine[];
  recommendations: CostRecommendation[];
  note_ar?: string;
  disabled?: boolean;
}

export interface CostSlice {
  category: string;
  amount: number;
}

/** حالة عرض الربحيّة الصادقة: available فقط حين توجد أرقام حقيقيّة؛ وإلّا سبب صريح. */
export interface ProfitabilityView {
  available: boolean;
  reason: string | null;
  revenue: number | null;
  totalCost: number | null;
  grossMargin: number | null;
  marginPercent: number | null;
  costPerUnit: number | null;
  currency: string;
  /** موجب = ربح · سالب = خسارة · null = غير معروف. */
  profitable: boolean | null;
}

/** يترجم استجابة الربحيّة إلى نموذج عرض صادق (لا يخترع صفراً مكان null). */
export function summarizeProfitability(resp: ProfitabilityResponse | null | undefined): ProfitabilityView {
  const empty: ProfitabilityView = {
    available: false,
    reason: 'لا بيانات ربحيّة بعد.',
    revenue: null,
    totalCost: null,
    grossMargin: null,
    marginPercent: null,
    costPerUnit: null,
    currency: 'YER',
    profitable: null,
  };
  if (!resp) return empty;
  if (resp.disabled) return { ...empty, reason: 'سجلّ التكاليف غير مفعّل.' };
  if (!resp.profitability) return { ...empty, reason: resp.note_ar ?? 'لا سجلّ تكاليف/إيرادات لهذا الموسم بعد.' };
  const p = resp.profitability;
  return {
    available: true,
    reason: null,
    revenue: p.revenue,
    totalCost: p.total_cost,
    grossMargin: p.gross_margin,
    marginPercent: p.margin_percent,
    costPerUnit: p.cost_per_unit,
    currency: p.currency || 'YER',
    profitable: p.gross_margin > 0 ? true : p.gross_margin < 0 ? false : null,
  };
}

/** يرتّب تفصيل التكلفة تنازليّاً (أكبر بند أولاً)؛ يتجاهل البنود الصفريّة/السالبة. */
export function rankCostBreakdown(breakdown: Record<string, number> | null | undefined): CostSlice[] {
  if (!breakdown) return [];
  return Object.entries(breakdown)
    .map(([category, amount]) => ({ category, amount: Number(amount) || 0 }))
    .filter((s) => s.amount > 0)
    .sort((a, b) => b.amount - a.amount);
}

/** أعلى الانحرافات بالقيمة المطلقة (أهمّها للانتباه) — الأكبر أثراً أولاً. */
export function topVariances(variance: VarianceLine[] | null | undefined, limit = 3): VarianceLine[] {
  if (!Array.isArray(variance)) return [];
  return [...variance]
    .sort((a, b) => Math.abs(b.variance_amount) - Math.abs(a.variance_amount))
    .slice(0, limit);
}

/** تنسيق مبلغ صادق: null ⇒ «—» (لا صفر مُلفَّق)؛ وإلّا رقم مقرَّب + عملة. */
export function formatMoney(value: number | null | undefined, currency = 'YER'): string {
  if (value == null || !Number.isFinite(value)) return '—';
  const rounded = Math.round(value);
  return `${rounded.toLocaleString('en-US')} ${currency}`;
}

/** تنسيق نسبة مئويّة صادق: null ⇒ «—». */
export function formatPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value.toFixed(1)}٪`;
}
