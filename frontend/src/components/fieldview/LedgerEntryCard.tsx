import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { PenLine, CheckCircle2 } from 'lucide-react';
import {
  useRecordLedgerOperation, useUpsertBudgetLines, useRecordRevenue, LEDGER_QUERY_PREFIXES,
} from '../../hooks/useApi';
import {
  buildBudgetPayload, buildOperationPayload, buildRevenuePayload,
  COST_CATEGORIES, OPERATION_TYPES,
} from '../../lib/ledgerEntry';
import { T } from '../ds';

interface Props {
  fieldId?: string | null;
  seasonId?: string | null;
  /** اليوم ISO — التاريخ الافتراضيّ للنماذج. */
  todayIso: string;
  enabled?: boolean;
}

const CAT_AR: Record<string, string> = {
  labor: 'عمالة', water: 'ريّ', energy: 'طاقة', fertilizer: 'تسميد', seed: 'بذار',
  pesticide: 'مكافحة', equipment: 'معدّات', fuel: 'وقود', overhead: 'غير مباشرة',
};
const OP_AR: Record<string, string> = {
  irrigation: 'ريّ', fertilization: 'تسميد', spray: 'رشّ', plowing: 'حراثة',
  sowing: 'بذار', harvest: 'حصاد', maintenance: 'صيانة', other: 'أخرى',
};

type Tab = 'operation' | 'budget' | 'revenue';

/** إدخال السجلّ الماليّ: عمليّة بتكلفة · بند موازنة · إيراد — يكتمل به القوس
 *  (موازنة ⇒ عمليّات ⇒ إيراد ⇒ ربحيّة/انحراف) من الشاشة. صدق: تحقّق محليّ صارم
 *  برسائل عربيّة، النجاح يُبطل كاش الربحيّة فتتحدّث حيّاً، والفشل يُعرَض لا يُبتلَع. */
export default function LedgerEntryCard({ fieldId, seasonId, todayIso, enabled = true }: Props) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>('operation');
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);

  // عمليّة
  const [opDate, setOpDate] = useState(todayIso);
  const [opType, setOpType] = useState('irrigation');
  const [opCost, setOpCost] = useState('');
  const [opCat, setOpCat] = useState('water');
  const opM = useRecordLedgerOperation();
  // موازنة
  const [budgetCat, setBudgetCat] = useState('fertilizer');
  const [budgetCost, setBudgetCost] = useState('');
  const budgetM = useUpsertBudgetLines();
  // إيراد
  const [revDate, setRevDate] = useState(todayIso);
  const [revProduct, setRevProduct] = useState('');
  const [revAmount, setRevAmount] = useState('');
  const revM = useRecordRevenue();

  if (!enabled || !fieldId) return null;

  const invalidate = () => {
    for (const prefix of LEDGER_QUERY_PREFIXES) qc.invalidateQueries({ queryKey: [prefix] });
  };
  const afterSuccess = (text: string) => { setMsg({ tone: 'ok', text }); invalidate(); };
  const afterError = (e: unknown) => {
    const status = (e as { response?: { status?: number } })?.response?.status;
    setMsg({
      tone: 'err',
      text: status === 404
        ? 'سجلّ التكاليف غير مفعّل (FEATURE_FARM_OPERATIONS_LEDGER).'
        : status === 403
          ? 'دورك لا يخوّل الإدخال (يتطلّب صلاحيّة تنفيذ).'
          : `تعذّر الحفظ${status ? ` (${status})` : ''} — لم يُسجَّل شيء.`,
    });
  };

  const submitOperation = () => {
    setMsg(null);
    const r = buildOperationPayload({ operationDate: opDate, operationType: opType, costAmount: opCost, costCategory: opCat, fieldId, seasonId });
    if (!r.ok) { setMsg({ tone: 'err', text: r.error }); return; }
    opM.mutate(r.payload, { onSuccess: () => { setOpCost(''); afterSuccess('سُجِّلت العمليّة بتكلفتها في السجلّ.'); }, onError: afterError });
  };
  const submitBudget = () => {
    setMsg(null);
    const r = buildBudgetPayload({ seasonId: seasonId ?? null, category: budgetCat, plannedCost: budgetCost });
    if (!r.ok) { setMsg({ tone: 'err', text: r.error }); return; }
    budgetM.mutate(r.payload, { onSuccess: () => { setBudgetCost(''); afterSuccess('أُدرج بند الموازنة المخطَّط.'); }, onError: afterError });
  };
  const submitRevenue = () => {
    setMsg(null);
    const r = buildRevenuePayload({ seasonId: seasonId ?? null, fieldId, revenueDate: revDate, productName: revProduct, amount: revAmount });
    if (!r.ok) { setMsg({ tone: 'err', text: r.error }); return; }
    revM.mutate(r.payload, { onSuccess: () => { setRevAmount(''); afterSuccess('سُجِّل الإيراد للموسم.'); }, onError: afterError });
  };

  const pending = opM.isPending || budgetM.isPending || revM.isPending;
  const inputStyle = { border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink } as const;

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="ledger-entry" aria-label="إدخال السجلّ الماليّ">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <PenLine className="w-4 h-4 text-emerald-300" aria-hidden="true" /> إدخال السجلّ الماليّ
        </span>
        <div className="inline-flex items-center gap-1 rounded-xl p-0.5" style={{ background: T.card, border: `1px solid ${T.line}` }}>
          {([['operation', 'عمليّة'], ['budget', 'موازنة'], ['revenue', 'إيراد']] as [Tab, string][]).map(([t, label]) => (
            <button
              key={t}
              type="button"
              onClick={() => { setTab(t); setMsg(null); }}
              className="px-2.5 py-0.5 rounded-lg text-[11px] font-bold"
              style={{ background: tab === t ? '#14532d' : 'transparent', color: tab === t ? '#bbf7d0' : T.muted }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'operation' && (
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
          <input type="date" value={opDate} onChange={(e) => setOpDate(e.target.value)} className="px-2 py-1 rounded-lg" style={inputStyle} aria-label="تاريخ العمليّة" />
          <select value={opType} onChange={(e) => setOpType(e.target.value)} className="px-2 py-1 rounded-lg" style={inputStyle} aria-label="نوع العمليّة">
            {OPERATION_TYPES.map((o) => <option key={o} value={o}>{OP_AR[o] ?? o}</option>)}
          </select>
          <input type="number" min="0" step="1" value={opCost} onChange={(e) => setOpCost(e.target.value)} placeholder="التكلفة" className="w-24 px-2 py-1 rounded-lg" style={inputStyle} aria-label="مبلغ التكلفة" />
          <select value={opCat} onChange={(e) => setOpCat(e.target.value)} className="px-2 py-1 rounded-lg" style={inputStyle} aria-label="فئة التكلفة">
            {COST_CATEGORIES.map((c) => <option key={c} value={c}>{CAT_AR[c] ?? c}</option>)}
          </select>
          <button type="button" onClick={submitOperation} disabled={pending} className="px-2.5 py-1 rounded-lg font-semibold disabled:opacity-50" style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}>
            {opM.isPending ? 'جارٍ الحفظ…' : 'سجِّل العمليّة'}
          </button>
        </div>
      )}

      {tab === 'budget' && (
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
          <select value={budgetCat} onChange={(e) => setBudgetCat(e.target.value)} className="px-2 py-1 rounded-lg" style={inputStyle} aria-label="فئة الموازنة">
            {COST_CATEGORIES.map((c) => <option key={c} value={c}>{CAT_AR[c] ?? c}</option>)}
          </select>
          <input type="number" min="0" step="1" value={budgetCost} onChange={(e) => setBudgetCost(e.target.value)} placeholder="المخطَّط للموسم" className="w-32 px-2 py-1 rounded-lg" style={inputStyle} aria-label="المبلغ المخطَّط" />
          <button type="button" onClick={submitBudget} disabled={pending} className="px-2.5 py-1 rounded-lg font-semibold disabled:opacity-50" style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}>
            {budgetM.isPending ? 'جارٍ الحفظ…' : 'أدرِج البند'}
          </button>
          <span className="text-[10px]" style={{ color: T.faint }}>يُقارَن مع الفعليّ في «أبرز انحراف».</span>
        </div>
      )}

      {tab === 'revenue' && (
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
          <input type="date" value={revDate} onChange={(e) => setRevDate(e.target.value)} className="px-2 py-1 rounded-lg" style={inputStyle} aria-label="تاريخ الإيراد" />
          <input value={revProduct} onChange={(e) => setRevProduct(e.target.value)} placeholder="المنتَج (اختياريّ)" className="w-28 px-2 py-1 rounded-lg" style={inputStyle} aria-label="اسم المنتَج" />
          <input type="number" min="0" step="1" value={revAmount} onChange={(e) => setRevAmount(e.target.value)} placeholder="المبلغ" className="w-28 px-2 py-1 rounded-lg" style={inputStyle} aria-label="مبلغ الإيراد" />
          <button type="button" onClick={submitRevenue} disabled={pending} className="px-2.5 py-1 rounded-lg font-semibold disabled:opacity-50" style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}>
            {revM.isPending ? 'جارٍ الحفظ…' : 'سجِّل الإيراد'}
          </button>
        </div>
      )}

      {msg && (
        <div className="mt-2 inline-flex items-center gap-1.5 text-[11px]" role="status" style={{ color: msg.tone === 'ok' ? '#86efac' : '#fdba74' }}>
          {msg.tone === 'ok' && <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />}
          {msg.text}
        </div>
      )}
    </section>
  );
}
