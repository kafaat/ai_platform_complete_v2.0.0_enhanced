import { useRef, useState } from 'react';
import { readWheatReferences, wheatCultivars, type WheatReference } from '../lib/wheatRegister';

type Selection = { variety: string; rate: string; note: string; irrigation: string };
export default function WheatSeasonPlanner({ onApply, initialRefs = [], initialSource = '', easternRainfed = false, confirmation }: { onApply: (plan: Selection) => void; initialRefs?: WheatReference[]; initialSource?: string; easternRainfed?: boolean; confirmation?: string }) {
  const [refs, setRefs] = useState<WheatReference[]>(initialRefs);
  const [source, setSource] = useState(initialSource);
  const [variety, setVariety] = useState('');
  const [sheet, setSheet] = useState('');
  const [area, setArea] = useState('');
  const [rate, setRate] = useState('');
  const [stock, setStock] = useState('');
  const [price, setPrice] = useState('');
  const [irrigation, setIrrigation] = useState('');
  const [message, setMessage] = useState('');
  const [east, setEast] = useState(easternRainfed);
  const version = useRef(0);
  const ref = refs.find(r => r.sheet === sheet);
  const need = Number(area) > 0 && Number(rate) > 0 ? Number(area) * Number(rate) : null;
  const buy = need != null && stock !== '' && Number(stock) >= 0 ? Math.max(0, need - Number(stock)) : null;
  const estimate = buy != null && price !== '' && Number(price) >= 0 ? buy * Number(price) : null;
  const fmt = (n: number) => n.toLocaleString('ar', {maximumFractionDigits: 2});
  async function upload(file?: File) {
    const current = ++version.current;
    setSheet(''); setRate(''); setRefs([]); setSource(''); setEast(false); setMessage('');
    if (!file) return;
    try {
      const { default: read } = await import('read-excel-file/browser');
      const bytes = await file.arrayBuffer();
      const digest = globalThis.crypto?.subtle ? await crypto.subtle.digest('SHA-256', bytes) : null;
      const hash = digest && Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
      const list = readWheatReferences(await read(bytes));
      if (current !== version.current) return;
      setEast(hash === 'baecdd79d8498cad7cfce26bb18a8d1016b02aac9a821f57c33fdf963cbe0cad');
      setRefs(list); setSource(file.name);
      setMessage('عدد مراجع القمح الصالحة: ' + list.length);
    } catch { if (current === version.current) setMessage('تعذرت قراءة ملف Excel. يمكنك إدخال المعدل يدوياً.'); }
  }
  function choose(sheetName: string) {
    setSheet(sheetName);
    const item = refs.find(r => r.sheet === sheetName);
    setRate(item ? (item.seedKg / item.hectares).toFixed(2) : '');
  }
  function apply() {
    if (!need || !variety || !irrigation) return;
    const origin = ref ? source + ' / ' + sheet + (ref.rainfed && east ? ' · مزرعة الري المطري بين المحورين جهة الشرق' : '') : 'إدخال يدوي';
    const note = ['خطة بذار القمح', 'المرجع ' + origin, 'المساحة المخططة ' + area + ' هكتار',
      stock !== '' ? 'المتوفر ' + stock + ' كغ' : '', price !== '' ? 'سعر الكيلو ' + price + ' ريال' : '', 'الاحتياج ' + fmt(need) + ' كغ', buy != null ? 'شراء ' + fmt(buy) + ' كغ' : '',
      estimate != null ? 'كلفة شراء مقدرة ' + fmt(estimate) + ' ريال يمني' : ''].filter(Boolean).join(' · ');
    onApply({ variety, rate, irrigation, note }); setMessage(confirmation ?? 'نُقلت الخطة إلى نموذج الموسم. راجع الحقل والتاريخ ثم احفظ.');
  }
  return <details open={initialRefs.length > 0 || undefined} dir="rtl" className="rounded-xl border border-slate-600 p-3">
    <summary>تخطيط بذار القمح من سجل الزراعة</summary>
    <div className="mt-3 grid gap-3">
      <label>سجل الزراعة Excel <input type="file" accept=".xlsx" onChange={e => void upload(e.target.files?.[0])} /></label>
      <label>صنف القمح <select value={variety} onChange={e => {setVariety(e.target.value); choose(''); setStock(''); setPrice('');}}>
        <option value="">اختر الصنف</option>{wheatCultivars.map(v => <option key={v}>{v}</option>)}</select></label>
      <label>مرجع البذار <select value={sheet} onChange={e => choose(e.target.value)}>
        <option value="">معدل يدوي</option>{refs.filter(r => r.variety === variety).map(r => <option key={r.sheet}>{r.sheet}</option>)}</select></label>
      {ref && <p>{ref.day} · {fmt(ref.seedKg)} كغ على {fmt(ref.hectares * 10000)} م²</p>}
      {ref?.rainfed && <label><input type="checkbox" checked={east} onChange={e => setEast(e.target.checked)} /> مرجع هذه الورقة هو مزرعة الري المطري بين المحورين جهة الشرق</label>}
      <label>ري الموسم الجديد <select value={irrigation} onChange={e => setIrrigation(e.target.value)}><option value="">اختر</option><option value="pivot">محوري</option><option value="rainfed">مطري</option></select></label>
      <label>المساحة المخططة بالهكتار <input type="number" min="0" step="any" value={area} onChange={e => setArea(e.target.value)} /></label>
      <label>معدل البذار المخطط كغ/هكتار <input type="number" min="0" step="0.01" value={rate} onChange={e => setRate(e.target.value)} /></label>
      <label>المخزون الصالح من الصنف بالكيلوغرام <input type="number" min="0" step="any" value={stock} onChange={e => setStock(e.target.value)} /></label>
      <label>سعر شراء الكيلو بالريال اليمني <input type="number" min="0" step="any" value={price} onChange={e => setPrice(e.target.value)} /></label>
      {need != null && <output>الاحتياج {fmt(need)} كغ{buy != null && ' · الشراء ' + fmt(buy) + ' كغ'}{estimate != null && ' · الموازنة ' + fmt(estimate) + ' ريال'}</output>}
      <button type="button" disabled={!variety || !need || !irrigation || Number(stock)<0 || Number(price)<0} onClick={apply}>استخدام الخطة في الموسم</button>
      <span role="status">{message}</span>
    </div>
  </details>;
}
