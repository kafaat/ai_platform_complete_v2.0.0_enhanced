// FieldView Harvest Traceability — يعكس سلسلة «من المزرعة إلى السوق» المُخزَّنة
// (/api/v1/harvest-lots + custody_chain_events append-only + input-traceability)
// على الحقل النشط. صدق: الاكتمال من معيار الخادم (بدأت بحصاد ∧ بلغت بيعاً)، كلفة
// المدخلات الغائبة تُعلَن بنسبة تغطية لا تُؤلَّف، والكمّيّات null تبقى «—».

export interface HarvestLotSummary {
  harvest_lot_id: string;
  field_id: string;
  season_id?: string | null;
  crop?: string | null;
  harvest_date?: string | null;
  quantity_kg?: number | null;
  moisture_pct?: number | null;
  quality_grade?: string | null;
  status: string;
}

export interface CustodyEventSummary {
  custody_event_id: number;
  event_type: string;
  handler?: string | null;
  handler_role?: string | null;
  location_name?: string | null;
  quantity_kg?: number | null;
  occurred_at?: string | null;
}

export interface TraceabilityChainMeta {
  event_count: number;
  started_at_harvest: boolean;
  reached_market: boolean;
  complete: boolean;
}

export interface LotTraceability {
  harvest_lot: HarvestLotSummary;
  custody_chain: CustodyEventSummary[];
  origin: { field_id?: string; field_name?: string | null; area_ha?: number | null };
  chain: TraceabilityChainMeta;
}

export interface InputLedger {
  field_id: string;
  season_id?: string | null;
  state: string;
  by_input_type: Record<string, { count: number; cost: number; n_with_cost: number; products?: string[] }>;
  total_cost: number;
  cost_coverage: number;
  cost_per_ha?: number | null;
  cost_per_ton?: number | null;
  harvest_yield_t_ha?: number | null;
  area_ha?: number | null;
  currency?: string;
  reason_ar?: string;
}

export const EVENT_TYPE_AR: Record<string, string> = {
  harvest: 'حصاد',
  storage: 'تخزين',
  quality_check: 'فحص جودة',
  transport: 'نقل',
  sales: 'بيع',
};

export const INPUT_TYPE_AR: Record<string, string> = {
  seed: 'بذار',
  fertilizer: 'تسميد',
  pesticide: 'مكافحة',
  irrigation: 'ريّ',
};

/** حالة السلسلة بالعربيّة من معيار الخادم — لا نُعيد الحكم، نعرضه. */
export function chainStatusLabel(chain: TraceabilityChainMeta | null | undefined): string {
  if (!chain) return '—';
  if (chain.complete) return 'كاملة: من الحصاد إلى السوق';
  if (chain.started_at_harvest) return 'بدأت بالحصاد — لم تبلغ السوق بعد';
  if (chain.event_count > 0) return 'سلسلة بلا حدث حصاد مُسجَّل';
  return 'لا أحداث حيازة بعد';
}

export interface LotsOverview {
  count: number;
  /** مجموع الكمّيّات المعروفة فقط (كغ) — null إن لم تُعرَف أيّ كمّيّة. */
  knownQuantityKg: number | null;
  latest: HarvestLotSummary | null;
}

/** ملخّص دفعات الحقل — يجمع الكمّيّات الحقيقيّة فقط (null لا يُصفَّر). */
export function summarizeLots(lots: HarvestLotSummary[] | null | undefined): LotsOverview {
  if (!Array.isArray(lots) || lots.length === 0) return { count: 0, knownQuantityKg: null, latest: null };
  const known = lots.filter((l) => typeof l.quantity_kg === 'number');
  return {
    count: lots.length,
    knownQuantityKg: known.length ? known.reduce((s, l) => s + (l.quantity_kg as number), 0) : null,
    latest: lots[0] ?? null,
  };
}

export interface LedgerFact {
  label: string;
  value: string;
}

/** حقائق دفتر المدخلات — تغطية الكلفة تُعرَض صراحةً (الكلفة الغائبة تُعلَن لا تُؤلَّف). */
export function inputLedgerFacts(ledger: InputLedger | null | undefined): LedgerFact[] {
  if (!ledger || ledger.state === 'no_inputs') return [];
  const cur = ledger.currency || 'YER';
  const facts: LedgerFact[] = [];
  const types = Object.entries(ledger.by_input_type ?? {});
  if (types.length) {
    facts.push({
      label: 'مدخلات',
      value: types.map(([t, g]) => `${INPUT_TYPE_AR[t] ?? t}×${g.count}`).join(' · '),
    });
  }
  if (ledger.total_cost > 0) {
    const covPct = Math.round((ledger.cost_coverage ?? 0) * 100);
    facts.push({ label: 'كلفة المدخلات', value: `${Math.round(ledger.total_cost).toLocaleString('en-US')} ${cur} (تغطية ${covPct}٪)` });
  }
  if (ledger.cost_per_ha != null) facts.push({ label: 'كلفة/هـ', value: `${Math.round(ledger.cost_per_ha).toLocaleString('en-US')} ${cur}` });
  if (ledger.cost_per_ton != null) facts.push({ label: 'كلفة/طن', value: `${Math.round(ledger.cost_per_ton).toLocaleString('en-US')} ${cur}` });
  if (ledger.harvest_yield_t_ha != null) facts.push({ label: 'غلّة مُقاسة', value: `${ledger.harvest_yield_t_ha} طن/هـ` });
  return facts;
}
