import { useEffect, useMemo, useState } from 'react';
import { BookOpen, Download, Plus } from 'lucide-react';
import { kongApi } from '../services/api/client';

type Entry = {
  entry_id: string; occurred_on: string; entry_type: string; payment_method: string;
  category: string; amount: number; currency: string; party_id?: string | null;
  party_name?: string | null; settles_entry_id?: string | null;
};
type Party = { party_id: string; party_type: 'supplier' | 'customer' | 'both'; name: string };
type Summary = {
  status: string; currency?: string; total_expenses?: number; total_income?: number;
  net?: number; cash_balance_effect?: number; total_payable?: number; total_receivable?: number;
};

const box = 'rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100';

export default function SimpleFarmBookPage() {
  const today = new Date().toISOString().slice(0, 10);
  const month = today.slice(0, 7);
  const [farmId, setFarmId] = useState('');
  const [items, setItems] = useState<Entry[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [balances, setBalances] = useState<Summary | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    entry_type: 'expense', payment_method: 'cash', category: 'other_expense',
    amount: '', currency: 'YER', occurred_on: today, field_id: '', season_id: '',
    party_id: '', description: '', receipt_document_id: '',
    settles_entry_id: '',
  });
  const [partyForm, setPartyForm] = useState({ name: '', party_type: 'supplier' });
  const canSave = Boolean(
    farmId.trim() && Number(form.amount) > 0 &&
    (form.payment_method !== 'credit' || form.party_id) &&
    (form.entry_type !== 'payment' || (form.party_id && form.settles_entry_id))
  );
  const operationId = useMemo(() => () =>
    `web-${Date.now()}-${typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : Math.random().toString(16).slice(2)}`, []);

  async function refresh() {
    if (!farmId.trim()) return;
    setError('');
    try {
      const [entries, report, partyList, balanceReport] = await Promise.all([
        kongApi.get('/api/v1/farm-book/entries', { params: { farm_id: farmId.trim() } }),
        kongApi.get('/api/v1/farm-book/monthly', { params: { month, farm_id: farmId.trim() } }),
        kongApi.get('/api/v1/farm-book/parties'),
        kongApi.get('/api/v1/farm-book/balances', { params: { farm_id: farmId.trim(), as_of: today } }),
      ]);
      setItems(entries.data.items ?? []);
      setSummary(report.data.summary ?? null);
      setParties(partyList.data.items ?? []);
      setBalances(balanceReport.data.summary ?? null);
    } catch {
      setError('تعذّر تحميل دفتر المزرعة. تحقق من معرّف المزرعة والصلاحية.');
    }
  }

  useEffect(() => { void refresh(); }, []); // المستخدم يحمّل بعد إدخال المزرعة

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSave) return;
    setSaving(true); setError('');
    try {
      await kongApi.post('/api/v1/farm-book/entries', {
        client_operation_id: operationId(),
        farm_id: farmId.trim(),
        ...form,
        amount: Number(form.amount),
        field_id: form.field_id || null,
        season_id: form.season_id || null,
        party_id: form.party_id || null,
        description: form.description || null,
        receipt_document_id: form.receipt_document_id || null,
        settles_entry_id: form.settles_entry_id || null,
        payment_method: form.entry_type === 'payment' ? 'cash' : form.payment_method,
        category: form.entry_type === 'payment' ? 'debt_payment' : form.category,
      });
      setForm(v => ({ ...v, amount: '', description: '', receipt_document_id: '', settles_entry_id: '' }));
      await refresh();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'تعذّر حفظ الحركة.');
    } finally { setSaving(false); }
  }

  async function createParty(e: React.FormEvent) {
    e.preventDefault();
    if (!partyForm.name.trim()) return;
    setSaving(true); setError('');
    try {
      const res = await kongApi.post('/api/v1/farm-book/parties', {
        name: partyForm.name.trim(), party_type: partyForm.party_type,
      });
      setPartyForm(v => ({ ...v, name: '' }));
      setParties(v => [...v, res.data].sort((a, b) => a.name.localeCompare(b.name, 'ar')));
      set('party_id', res.data.party_id);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? 'تعذّر حفظ المورد أو العميل.');
    } finally { setSaving(false); }
  }

  async function download(format: 'csv' | 'pdf') {
    try {
      const res = await kongApi.get('/api/v1/farm-book/export', {
        params: { month, farm_id: farmId.trim(), format }, responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url; a.download = `farm_book_${month}.${format}`; a.click();
      URL.revokeObjectURL(url);
    } catch { setError('تعذّر تصدير التقرير.'); }
  }

  const set = (key: keyof typeof form, value: string) => setForm(v => ({ ...v, [key]: value }));
  return (
    <main dir="rtl" className="space-y-4 p-4 text-slate-100">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-bold"><BookOpen /> دفتر المزرعة البسيط</h1>
        <p className="text-sm text-slate-400">مصروفات وإيرادات نقدية أو آجلة، دون تعقيد محاسبي.</p>
      </header>
      <section className="flex flex-wrap gap-2">
        <input className={box} value={farmId} onChange={e => setFarmId(e.target.value)} placeholder="معرّف المزرعة" />
        <button className={box} onClick={() => void refresh()}>تحميل</button>
        <button className={box} disabled={!farmId} onClick={() => void download('csv')}><Download className="inline h-4" /> CSV</button>
        <button className={box} disabled={!farmId} onClick={() => void download('pdf')}><Download className="inline h-4" /> PDF</button>
      </section>
      {error && <div className="rounded-xl border border-red-700 bg-red-950/40 p-3 text-sm">{error}</div>}
      {summary?.status === 'ok' && (
        <section className="grid grid-cols-2 gap-2 md:grid-cols-6">
          {[
            ['المصروف', summary.total_expenses], ['الإيراد', summary.total_income],
            ['الصافي', summary.net], ['أثر الصندوق', summary.cash_balance_effect],
            ['علينا', summary.total_payable], ['لنا', summary.total_receivable],
          ].map(([label, value]) => <div key={String(label)} className={box}><small>{label}</small><div className="font-bold">{Number(value ?? 0).toLocaleString()} {summary.currency}</div></div>)}
        </section>
      )}
      {balances?.status === 'ok' && (
        <section className="grid grid-cols-2 gap-2">
          <div className={box}><small>إجمالي ما علينا حتى اليوم</small><div className="font-bold">{Number(balances.total_payable ?? 0).toLocaleString()} {balances.currency}</div></div>
          <div className={box}><small>إجمالي ما لنا حتى اليوم</small><div className="font-bold">{Number(balances.total_receivable ?? 0).toLocaleString()} {balances.currency}</div></div>
        </section>
      )}
      <form onSubmit={createParty} className="flex flex-wrap gap-2 rounded-2xl border border-slate-700 bg-slate-950 p-4">
        <strong className="w-full text-sm">إضافة مورد أو عميل</strong>
        <input className={box} value={partyForm.name} onChange={e => setPartyForm(v => ({ ...v, name: e.target.value }))} placeholder="الاسم" />
        <select className={box} value={partyForm.party_type} onChange={e => setPartyForm(v => ({ ...v, party_type: e.target.value }))}>
          <option value="supplier">مورد</option><option value="customer">عميل</option><option value="both">مورد وعميل</option>
        </select>
        <button className="rounded-xl bg-sky-700 px-4 py-2 font-bold disabled:opacity-50" disabled={!partyForm.name.trim() || saving}>
          <Plus className="inline h-4" /> إضافة الطرف
        </button>
      </form>
      <form onSubmit={submit} className="grid gap-2 rounded-2xl border border-slate-700 bg-slate-950 p-4 md:grid-cols-4">
        <select className={box} value={form.entry_type} onChange={e => set('entry_type', e.target.value)}>
          <option value="expense">مصروف</option><option value="income">إيراد</option><option value="payment">سداد دين</option>
        </select>
        <select className={box} value={form.entry_type === 'payment' ? 'cash' : form.payment_method} disabled={form.entry_type === 'payment'} onChange={e => set('payment_method', e.target.value)}>
          <option value="cash">نقدي</option><option value="credit">آجل</option>
        </select>
        <input className={box} value={form.entry_type === 'payment' ? 'debt_payment' : form.category} disabled={form.entry_type === 'payment'} onChange={e => set('category', e.target.value)} placeholder="التصنيف" />
        <input className={box} type="number" min="0.01" step="0.01" value={form.amount} onChange={e => set('amount', e.target.value)} placeholder="المبلغ" />
        <input className={box} type="date" value={form.occurred_on} onChange={e => set('occurred_on', e.target.value)} />
        <select className={box} value={form.party_id} onChange={e => set('party_id', e.target.value)}>
          <option value="">بدون مورد/عميل</option>
          {parties.map(p => <option key={p.party_id} value={p.party_id}>{p.name} — {p.party_type === 'supplier' ? 'مورد' : p.party_type === 'customer' ? 'عميل' : 'الاثنان'}</option>)}
        </select>
        {form.entry_type === 'payment' && (
          <select className={box} value={form.settles_entry_id} onChange={e => {
            const original = items.find(item => item.entry_id === e.target.value);
            set('settles_entry_id', e.target.value);
            if (original?.party_id) set('party_id', original.party_id);
          }}>
            <option value="">اختر القيد الآجل المراد سداده</option>
            {items.filter(item => item.payment_method === 'credit' && item.entry_type !== 'payment').map(item =>
              <option key={item.entry_id} value={item.entry_id}>{item.occurred_on} — {item.party_name ?? 'طرف'} — {Number(item.amount).toLocaleString()} {item.currency}</option>
            )}
          </select>
        )}
        <input className={box} value={form.field_id} onChange={e => set('field_id', e.target.value)} placeholder="الحقل (اختياري)" />
        <input className={box} value={form.season_id} onChange={e => set('season_id', e.target.value)} placeholder="الموسم (اختياري)" />
        <input className={box} value={form.receipt_document_id} onChange={e => set('receipt_document_id', e.target.value)} placeholder="معرّف صورة الفاتورة" />
        <input className={`${box} md:col-span-2`} value={form.description} onChange={e => set('description', e.target.value)} placeholder="ملاحظة" />
        <button className="rounded-xl bg-emerald-600 px-4 py-2 font-bold disabled:opacity-50" disabled={!canSave || saving}>
          <Plus className="inline h-4" /> {saving ? 'جارٍ الحفظ…' : 'حفظ الحركة'}
        </button>
      </form>
      <section className="overflow-x-auto rounded-2xl border border-slate-700">
        <table className="w-full text-sm"><thead className="bg-slate-900"><tr>
          <th className="p-2">التاريخ</th><th>النوع</th><th>الدفع</th><th>التصنيف</th><th>الطرف</th><th>المبلغ</th><th>مرجع</th>
        </tr></thead><tbody>{items.map(e => <tr key={e.entry_id} className="border-t border-slate-800">
          <td className="p-2">{e.occurred_on}</td><td>{e.entry_type === 'expense' ? 'مصروف' : e.entry_type === 'income' ? 'إيراد' : 'سداد'}</td>
          <td>{e.payment_method === 'cash' ? 'نقدي' : 'آجل'}</td><td>{e.category}</td><td>{e.party_name ?? '—'}</td>
          <td>{Number(e.amount).toLocaleString()} {e.currency}</td>
          <td className="max-w-36 truncate font-mono text-xs" title={e.entry_id}>{e.entry_id}</td>
        </tr>)}</tbody></table>
      </section>
    </main>
  );
}
