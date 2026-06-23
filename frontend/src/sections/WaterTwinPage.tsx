// ═══════════════════════════════════════════════════════════════
// SAHOOL — WaterTwinPage (توأم المياه التفاعليّ — المرحلة الثانية)
// «ماذا لو أخّرتُ الريّ N يوماً؟ خفّضتُه X٪؟» → أثر على نضوب الجذور وأيّام الإجهاد
// واستهلاك الماء (مسار FAO-56 أماميّ، مُغذّى بدفتر المياه v98 للحقل).
// صدق: لا غلّة مُلفّقة — أيّام إجهاد/استهلاك ماء فقط؛ مصدر كلّ قيمة مُعلَن (من الدفتر أم الطلب).
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Droplets, GitCompare, Info, AlertTriangle } from 'lucide-react';
import { useFieldOptions } from '../hooks/useFieldOptions';
import { simulateFieldWaterTwin, asApiError } from '../services/api';
import type { FieldWaterTwinInput, WaterTwinResult } from '../services/api';

export default function WaterTwinPage() {
  const { options, isLoading: fieldsLoading } = useFieldOptions();
  const [fieldId, setFieldId] = useState('');
  const [taw, setTaw] = useState('100');
  const [raw, setRaw] = useState('40');
  const [horizon, setHorizon] = useState('7');
  const [baselineIrr, setBaselineIrr] = useState('6');
  const [rain, setRain] = useState('0');
  const [etcOverride, setEtcOverride] = useState('');
  const [initOverride, setInitOverride] = useState('');
  const [kind, setKind] = useState<'delay' | 'scale'>('scale');
  const [delayDays, setDelayDays] = useState(3);
  const [scalePct, setScalePct] = useState(80);

  const [result, setResult] = useState<WaterTwinResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const numOr = (s: string, d: number): number => {
    const n = Number(s);
    return s.trim() === '' || isNaN(n) ? d : n;
  };
  const optNum = (s: string): number | null => (s.trim() === '' ? null : numOr(s, 0));

  const onSimulate = () => {
    if (!fieldId) return;
    const horizonDays = Math.max(1, Math.min(60, Math.round(numOr(horizon, 7))));
    const payload: FieldWaterTwinInput = {
      taw_mm: numOr(taw, 100),
      raw_mm: numOr(raw, 40),
      horizon_days: horizonDays,
      baseline_irrigation_mm: numOr(baselineIrr, 0),
      daily_rain_mm: numOr(rain, 0),
      daily_etc_mm: optNum(etcOverride),
      initial_depletion_mm: optNum(initOverride),
      scenario_kind: kind,
      delay_days: kind === 'delay' ? delayDays : 0,
      scale_factor: kind === 'scale' ? scalePct / 100 : 1,
    };
    setLoading(true);
    setError(null);
    simulateFieldWaterTwin(fieldId, payload)
      .then(r => { setResult(r); })
      .catch(e => {
        const detail = asApiError(e)?.response?.data?.detail;
        setError(typeof detail === 'string' ? detail : 'تعذّرت المحاكاة.');
        setResult(null);
      })
      .finally(() => setLoading(false));
  };

  const inputCls = 'px-3 py-2 rounded-lg text-sm w-full';
  const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Droplets className="w-5 h-5 text-sky-400" />
        <h2 className="text-xl font-bold text-slate-100">توأم المياه (محاكاة تفاعليّة)</h2>
      </div>
      <p className="text-sm text-slate-400">
        «ماذا لو أخّرتُ الريّ أيّاماً؟ خفّضتُه نسبةً؟» — يحاكي مسار نضوب منطقة الجذور للأيّام القادمة
        (FAO-56) مُغذّى بأحدث صفوف <span className="text-slate-300">دفتر المياه</span> للحقل، ويقارن
        الأساس بالبديل. القيم <span className="text-amber-300">تقديريّة غير معايَرة</span>، و
        <span className="text-amber-300"> لا يُقدَّر أثر الغلّة</span> (غير مُنمذَج).
      </p>

      {/* Form */}
      <div className="rounded-xl border p-4 space-y-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <label className="flex flex-col gap-1 col-span-2 sm:col-span-3">
            <span className="text-xs text-slate-400">الحقل</span>
            <select value={fieldId} onChange={e => setFieldId(e.target.value)} className={inputCls} style={inputStyle}>
              <option value="">{fieldsLoading ? 'تحميل الحقول…' : 'اختر حقلاً'}</option>
              {options.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">TAW (مم)</span>
            <input value={taw} onChange={e => setTaw(e.target.value)} inputMode="decimal" className={inputCls} style={inputStyle} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">RAW (مم)</span>
            <input value={raw} onChange={e => setRaw(e.target.value)} inputMode="decimal" className={inputCls} style={inputStyle} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">الأفق (يوم)</span>
            <input value={horizon} onChange={e => setHorizon(e.target.value)} inputMode="numeric" className={inputCls} style={inputStyle} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">ريّ يوميّ أساس (مم)</span>
            <input value={baselineIrr} onChange={e => setBaselineIrr(e.target.value)} inputMode="decimal" className={inputCls} style={inputStyle} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">مطر يوميّ (مم)</span>
            <input value={rain} onChange={e => setRain(e.target.value)} inputMode="decimal" className={inputCls} style={inputStyle} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">ETc يوميّ (اختياريّ — وإلّا من الدفتر)</span>
            <input value={etcOverride} onChange={e => setEtcOverride(e.target.value)} inputMode="decimal" placeholder="من الدفتر" className={inputCls} style={inputStyle} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">نضوب ابتدائيّ (اختياريّ — وإلّا من الدفتر)</span>
            <input value={initOverride} onChange={e => setInitOverride(e.target.value)} inputMode="decimal" placeholder="من الدفتر" className={inputCls} style={inputStyle} />
          </label>
        </div>

        {/* Scenario sliders */}
        <div className="rounded-lg border p-3 space-y-3" style={{ borderColor: '#334155', background: '#0f1117' }}>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-slate-400">البديل:</span>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="radio" checked={kind === 'scale'} onChange={() => setKind('scale')} />
              <span className="text-slate-200">تخفيض الريّ</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="radio" checked={kind === 'delay'} onChange={() => setKind('delay')} />
              <span className="text-slate-200">تأجيل الريّ</span>
            </label>
          </div>
          {kind === 'scale' ? (
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">عمق الريّ في البديل: {scalePct}٪ من الأساس</span>
              <input type="range" min={0} max={100} step={5} value={scalePct}
                onChange={e => setScalePct(Number(e.target.value))} className="w-full" />
            </label>
          ) : (
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">تأجيل الريّ: {delayDays} يوم</span>
              <input type="range" min={0} max={14} step={1} value={delayDays}
                onChange={e => setDelayDays(Number(e.target.value))} className="w-full" />
            </label>
          )}
        </div>

        <button onClick={onSimulate} disabled={!fieldId || loading}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50"
          style={{ background: loading ? '#0369a1' : '#0ea5e9' }}>
          <GitCompare className="w-4 h-4" /> {loading ? 'محاكاة…' : 'حاكِ السيناريو'}
        </button>
        {!fieldId && <p className="text-xs text-slate-500">اختر حقلاً أوّلاً.</p>}
      </div>

      {error && (
        <div className="rounded-lg border p-3 flex items-start gap-2 text-sm"
          style={{ background: '#3f1d1d', borderColor: '#7f1d1d', color: '#fecaca' }}>
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" /> <span>{error}</span>
        </div>
      )}

      {result && (
        <div className="space-y-4">
          {/* مصدر التغذية (شفافيّة) */}
          <div className="rounded-lg border p-3 text-xs text-slate-400 flex items-start gap-2"
            style={{ background: '#1e293b', borderColor: '#334155' }}>
            <Info className="w-4 h-4 mt-0.5 shrink-0 text-sky-400" />
            <span>
              النضوب الابتدائيّ {result.seed.initial_depletion_mm} مم
              (مصدر: <code className="text-slate-300">{result.seed.initial_depletion_source}</code>) ·
              ETc يوميّ {result.seed.daily_etc_mm} مم
              (مصدر: <code className="text-slate-300">{result.seed.daily_etc_source}</code>) ·
              صفوف دفتر مستخدَمة: {result.seed.ledger_rows_used}
            </span>
          </div>

          <p className="text-sm text-slate-300">{result.summary_ar}</p>

          {/* جدول المقارنة */}
          <div className="rounded-xl border overflow-hidden" style={{ borderColor: '#334155' }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: '#0f1117' }}>
                  <th className="text-right px-3 py-2 text-slate-400 font-medium">المؤشّر</th>
                  <th className="text-center px-3 py-2 text-slate-400 font-medium">الأساس</th>
                  <th className="text-center px-3 py-2 text-slate-400 font-medium">البديل</th>
                  <th className="text-center px-3 py-2 text-slate-400 font-medium">الفرق</th>
                </tr>
              </thead>
              <tbody>
                {result.comparisons.map((c, i) => (
                  <tr key={i} style={{ background: i % 2 ? '#1e293b' : '#172033' }}>
                    <td className="px-3 py-2 text-slate-200">{c.metric_ar}</td>
                    <td className="px-3 py-2 text-center text-slate-300">{c.baseline} {c.unit}</td>
                    <td className="px-3 py-2 text-center text-slate-300">{c.scenario} {c.unit}</td>
                    <td className="px-3 py-2 text-center font-medium"
                      style={{ color: c.delta > 0 ? '#fca5a5' : c.delta < 0 ? '#86efac' : '#94a3b8' }}>
                      {c.delta > 0 ? '+' : ''}{c.delta} {c.unit}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* مسار النضوب اليوميّ */}
          <div className="rounded-xl border overflow-x-auto" style={{ borderColor: '#334155' }}>
            <table className="w-full text-xs">
              <thead>
                <tr style={{ background: '#0f1117' }}>
                  <th className="px-2 py-2 text-slate-400 font-medium">يوم</th>
                  <th className="px-2 py-2 text-slate-400 font-medium">نضوب الأساس (مم)</th>
                  <th className="px-2 py-2 text-slate-400 font-medium">نضوب البديل (مم)</th>
                  <th className="px-2 py-2 text-slate-400 font-medium">إجهاد البديل؟</th>
                </tr>
              </thead>
              <tbody>
                {result.scenario.states.map((s, i) => {
                  const b = result.baseline.states[i];
                  return (
                    <tr key={s.day} style={{ background: i % 2 ? '#1e293b' : '#172033' }}>
                      <td className="px-2 py-1.5 text-center text-slate-300">{s.day}</td>
                      <td className="px-2 py-1.5 text-center text-slate-300">{b ? b.depletion_mm : '—'}</td>
                      <td className="px-2 py-1.5 text-center text-slate-300">{s.depletion_mm}</td>
                      <td className="px-2 py-1.5 text-center">
                        {s.stressed
                          ? <span className="text-orange-300">إجهاد</span>
                          : <span className="text-emerald-400">سليم</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
