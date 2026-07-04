// Ledger Entry — بناة حمولات إدخال السجلّ الماليّ (عمليّة بتكلفة · بند موازنة · إيراد)
// لنقاط farm-ledger POST. يُكمل قوس الربحيّة: قبل هذا كانت الواجهة تقرأ سجلّاً لا
// يستطيع المستخدم تعبئته إلّا عبر API. صدق: تحقّق صارم قبل الإرسال (مبالغ موجبة
// منتهية، حقول إلزاميّة) — نرفض محليّاً برسالة عربيّة واضحة بدل 422 غامضة، ولا
// نُرسل صفراً مُلفَّقاً؛ الخادم يبقى الحكم النهائيّ (ACTIVITY_EXECUTE + قيوده).

export type BuildResult<T> = { ok: true; payload: T } | { ok: false; error: string };

function positiveAmount(value: string | number | null | undefined, label: string): number | string {
  const n = typeof value === 'number' ? value : Number(String(value ?? '').trim());
  if (!Number.isFinite(n) || n <= 0) return `${label} يجب أن يكون رقماً موجباً.`;
  return n;
}

function isoDate(value: string | null | undefined, label: string): string | null {
  const d = String(value ?? '').slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : null;
}

// فئات التكلفة المعتمدة في السجلّ (تطابق تفصيل summary/cost_breakdown).
export const COST_CATEGORIES = ['labor', 'water', 'energy', 'fertilizer', 'seed', 'pesticide', 'equipment', 'fuel', 'overhead'] as const;
export const OPERATION_TYPES = ['irrigation', 'fertilization', 'spray', 'plowing', 'sowing', 'harvest', 'maintenance', 'other'] as const;

export interface OperationEntryInput {
  operationDate: string;
  operationType: string;
  costAmount: string | number;
  costCategory: string;
  fieldId: string | null;
  seasonId?: string | null;
  notes?: string;
}

export interface OperationPayload {
  operation_date: string;
  operation_type: string;
  field_id: string;
  season_id?: string;
  cost_amount: number;
  cost_category: string;
  status: 'completed';
  notes?: string;
}

export function buildOperationPayload(input: OperationEntryInput): BuildResult<OperationPayload> {
  const date = isoDate(input.operationDate, 'تاريخ العمليّة');
  if (!date) return { ok: false, error: 'تاريخ العمليّة مطلوب (YYYY-MM-DD).' };
  if (!input.operationType) return { ok: false, error: 'نوع العمليّة مطلوب.' };
  if (!input.fieldId) return { ok: false, error: 'لا حقل نشط لتسجيل العمليّة عليه.' };
  const amount = positiveAmount(input.costAmount, 'مبلغ التكلفة');
  if (typeof amount === 'string') return { ok: false, error: amount };
  if (!input.costCategory) return { ok: false, error: 'فئة التكلفة مطلوبة.' };
  const payload: OperationPayload = {
    operation_date: date,
    operation_type: input.operationType,
    field_id: input.fieldId,
    cost_amount: amount,
    cost_category: input.costCategory,
    status: 'completed',
  };
  if (input.seasonId) payload.season_id = input.seasonId;
  if (input.notes?.trim()) payload.notes = input.notes.trim();
  return { ok: true, payload };
}

export interface BudgetEntryInput {
  seasonId: string | null;
  category: string;
  plannedCost: string | number;
  notes?: string;
}

export interface BudgetLinesPayload {
  lines: {
    season_id: string;
    stage: 'whole_season';
    category: string;
    planned_cost: number;
    source: 'manual';
    notes?: string;
  }[];
}

export function buildBudgetPayload(input: BudgetEntryInput): BuildResult<BudgetLinesPayload> {
  if (!input.seasonId) return { ok: false, error: 'لا موسم نشط لربط بند الموازنة به.' };
  if (!input.category) return { ok: false, error: 'فئة الموازنة مطلوبة.' };
  const amount = positiveAmount(input.plannedCost, 'المبلغ المخطَّط');
  if (typeof amount === 'string') return { ok: false, error: amount };
  const line: BudgetLinesPayload['lines'][number] = {
    season_id: input.seasonId,
    stage: 'whole_season',
    category: input.category,
    planned_cost: amount,
    source: 'manual',
  };
  if (input.notes?.trim()) line.notes = input.notes.trim();
  return { ok: true, payload: { lines: [line] } };
}

export interface RevenueEntryInput {
  seasonId: string | null;
  fieldId?: string | null;
  revenueDate: string;
  productName?: string;
  amount: string | number;
  quantity?: string | number | null;
  unit?: string | null;
}

export interface RevenuePayload {
  season_id: string;
  field_id?: string;
  revenue_date: string;
  product_name?: string;
  amount: number;
  quantity?: number;
  unit?: string;
  source: 'manual';
}

export function buildRevenuePayload(input: RevenueEntryInput): BuildResult<RevenuePayload> {
  if (!input.seasonId) return { ok: false, error: 'لا موسم نشط لربط الإيراد به.' };
  const date = isoDate(input.revenueDate, 'تاريخ الإيراد');
  if (!date) return { ok: false, error: 'تاريخ الإيراد مطلوب (YYYY-MM-DD).' };
  const amount = positiveAmount(input.amount, 'مبلغ الإيراد');
  if (typeof amount === 'string') return { ok: false, error: amount };
  const payload: RevenuePayload = {
    season_id: input.seasonId,
    revenue_date: date,
    amount,
    source: 'manual',
  };
  if (input.fieldId) payload.field_id = input.fieldId;
  if (input.productName?.trim()) payload.product_name = input.productName.trim();
  // الكمّيّة اختياريّة — إن أُدخلت يجب أن تكون موجبة (لا نرسل قيماً فاسدة بصمت).
  if (input.quantity != null && String(input.quantity).trim() !== '') {
    const qty = positiveAmount(input.quantity, 'الكمّيّة');
    if (typeof qty === 'string') return { ok: false, error: qty };
    payload.quantity = qty;
    if (input.unit?.trim()) payload.unit = input.unit.trim();
  }
  return { ok: true, payload };
}
