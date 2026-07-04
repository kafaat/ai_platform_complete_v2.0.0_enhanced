import { useState } from 'react';
import { Wallet, ChevronDown } from 'lucide-react';
import { computeFieldEconomics } from '../../lib/fieldEconomics';
import { T } from '../ds';

interface Props {
  areaHa?: number | null;
  currency?: string;
}

const parse = (v: string): number | null => {
  const n = Number(v);
  return v.trim() !== '' && Number.isFinite(n) ? n : null;
};

/** طبقة أعمال الحقل: حاسبة تكلفة/ربحيّة صادقة — الأرقام يُدخِلها المستخدم، والرياضيّات نقيّة. */
export default function FieldEconomicsCard({ areaHa, currency = 'ر.ي' }: Props) {
  const [open, setOpen] = useState(false);
  const [irrigation, setIrrigation] = useState('');
  const [labor, setLabor] = useState('');
  const [inputs, setInputs] = useState('');
  const [other, setOther] = useState('');
  const [yieldT, setYieldT] = useState('');
  const [price, setPrice] = useState('');

  const e = computeFieldEconomics({
    areaHa: areaHa ?? null,
    irrigationCost: parse(irrigation),
    laborCost: parse(labor),
    inputsCost: parse(inputs),
    otherCost: parse(other),
    yieldTPerHa: parse(yieldT),
    pricePerT: parse(price),
    currency,
  });

  const fmt = (n: number | null, unit = '') =>
    n == null ? '—' : `${Math.round(n).toLocaleString('en-US')}${unit ? ` ${unit}` : ''}`;

  const fields: Array<[string, string, (v: string) => void, string]> = [
    ['ريّ', irrigation, setIrrigation, `تكلفة الريّ (${currency})`],
    ['عمالة', labor, setLabor, `تكلفة العمالة (${currency})`],
    ['مدخلات', inputs, setInputs, `سماد/رشّ/بذار (${currency})`],
    ['أخرى', other, setOther, `تكاليف أخرى (${currency})`],
    ['إنتاج', yieldT, setYieldT, 'إنتاج طن/هكتار'],
    ['سعر', price, setPrice, `سعر الطن (${currency})`],
  ];

  return (
    <section className="mb-3 rounded-2xl border" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="field-economics">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 p-3"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Wallet className="w-4 h-4 text-emerald-300" aria-hidden="true" /> تكلفة وربحيّة الحقل
        </span>
        <span className="inline-flex items-center gap-2 text-xs" style={{ color: T.muted }}>
          {e.hasAnyCost ? `التكلفة ${fmt(e.totalCost, currency)}` : 'أدخل التكاليف'}
          <ChevronDown className="w-4 h-4 transition-transform" style={{ transform: open ? 'rotate(180deg)' : 'none' }} aria-hidden="true" />
        </span>
      </button>

      {open && (
        <div className="px-3 pb-3">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-3">
            {fields.map(([label, val, set, ph]) => (
              <label key={label} className="flex flex-col gap-1 text-[11px]" style={{ color: T.muted }}>
                {ph}
                <input
                  type="number"
                  inputMode="decimal"
                  value={val}
                  onChange={(ev) => set(ev.target.value)}
                  placeholder="0"
                  className="px-2 py-1.5 rounded-lg text-sm"
                  style={{ background: T.card, border: `1px solid ${T.line}`, color: T.ink }}
                  aria-label={ph}
                />
              </label>
            ))}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Stat label="التكلفة الكلّيّة" value={e.hasAnyCost ? fmt(e.totalCost, currency) : '—'} />
            <Stat label="التكلفة/هكتار" value={fmt(e.costPerHa, currency)} />
            <Stat label="الإيراد المتوقَّع" value={fmt(e.revenue, currency)} />
            <Stat
              label="صافي الربح"
              value={fmt(e.netProfit, currency)}
              tone={e.netProfit == null ? undefined : e.netProfit >= 0 ? '#86efac' : '#fca5a5'}
              sub={e.marginPct != null ? `هامش ${Math.round(e.marginPct)}%` : undefined}
            />
          </div>

          <div className="mt-2 text-[10px]" style={{ color: T.faint }}>
            الأرقام مُدخَلة يدويّاً — لا تكاليف مُقدَّرة تلقائيّاً. (ربط سجلّ الريّ لاحقاً يملأ تكلفة الريّ تلقائيّاً.)
          </div>
        </div>
      )}
    </section>
  );
}

function Stat({ label, value, tone, sub }: { label: string; value: string; tone?: string; sub?: string }) {
  return (
    <div className="rounded-xl border p-2" style={{ borderColor: T.line }}>
      <div className="text-[10px]" style={{ color: T.faint }}>{label}</div>
      <div className="text-base font-extrabold" style={{ color: tone ?? T.ink }}>{value}</div>
      {sub && <div className="text-[10px]" style={{ color: T.muted }}>{sub}</div>}
    </div>
  );
}
