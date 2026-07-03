// ═══════════════════════════════════════════════════════════════
// SAHOOL — EtcDualPage (ETc المزدوج FAO-56، مُغذّى بـNDVI الحيّ — #462)
// يحسب ETc بنهج المعامل المزدوج: ETc = (Kcb·Ks + Ke)·ET0 (FAO-56 Ch.7)،
// مع اشتقاق Kcb رصداً من NDVI الحقل حين يتوفّر (وإلّا من العمر — تدرّج صادق).
// صدق: القيم تقديريّة غير معايَرة؛ مصدر كلّ قيمة مُعلَن (NDVI/الملوحة من الحقل أم الطلب)؛
// تُعرَض كلّ افتراضات المحرّك ولا تُخفى. لا تُعرَض قيمة لا يردّها الخادم.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Droplets, Calculator, Info, AlertTriangle, Satellite } from 'lucide-react';
import { useSelectedField } from '../hooks/useSelectedField';
import { computeFieldEtcDual, asApiError } from '../services/api';
import type { EtcDualInput, EtcDualResult } from '../services/api';

export default function EtcDualPage() {
  const { options, isLoading: fieldsLoading, fieldId, setFieldId } = useSelectedField();
  // الطقس (لـET0 — يمرّره المتّصِل)
  const [tMax, setTMax] = useState('35');
  const [tMin, setTMin] = useState('20');
  const [humidity, setHumidity] = useState('45');
  const [wind, setWind] = useState('2');
  const [solar, setSolar] = useState('25');
  const [lat, setLat] = useState('24.7');
  const [elevation, setElevation] = useState('600');
  const [doy, setDoy] = useState('175');
  // تجاوزات اختياريّة تسبق الحقن من الحقل
  const [ndviOverride, setNdviOverride] = useState('');
  const [dasOverride, setDasOverride] = useState('');

  const [result, setResult] = useState<EtcDualResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const numOr = (s: string, d: number): number => {
    const n = Number(s);
    return s.trim() === '' || isNaN(n) ? d : n;
  };
  const optNum = (s: string): number | null => {
    if (s.trim() === '') return null;
    const n = Number(s);
    return isNaN(n) ? null : n;
  };

  const onCompute = () => {
    if (!fieldId) return;
    const dasParsed = optNum(dasOverride);
    const payload: EtcDualInput = {
      temp_max_c: numOr(tMax, 35),
      temp_min_c: numOr(tMin, 20),
      humidity_pct: Math.max(0, Math.min(100, numOr(humidity, 45))),
      wind_speed_m_s: Math.max(0, numOr(wind, 2)),
      solar_radiation_mj_m2: Math.max(0, numOr(solar, 25)),
      latitude_deg: Math.max(-90, Math.min(90, numOr(lat, 24.7))),
      elevation_m: numOr(elevation, 0),
      day_of_year: Math.max(1, Math.min(366, Math.round(numOr(doy, 175)))),
      ndvi: optNum(ndviOverride),
      days_after_planting: dasParsed === null ? null : Math.max(0, Math.round(dasParsed)),
    };
    setLoading(true);
    setError(null);
    computeFieldEtcDual(fieldId, payload)
      .then(r => { setResult(r); })
      .catch(e => {
        const detail = asApiError(e)?.response?.data?.detail;
        setError(typeof detail === 'string' ? detail : 'تعذّر حساب ETc المزدوج.');
        setResult(null);
      })
      .finally(() => setLoading(false));
  };

  const inputCls = 'px-3 py-2 rounded-lg text-sm w-full';
  const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

  // صفوف نتيجة المعاملات (كلّها من ردّ الخادم — لا تلفيق).
  const metricRows: { label: string; value: number | string; unit?: string }[] = result
    ? [
        { label: 'ET0 (مرجعيّ)', value: result.et0_mm, unit: 'مم/يوم' },
        { label: 'Kcb (الأساس)', value: result.kcb },
        { label: 'Ks (إجهاد ملحيّ)', value: result.ks },
        { label: 'Ke (تبخّر سطحيّ)', value: result.ke },
        { label: 'Kc المزدوج (Kcb·Ks + Ke)', value: result.kc_dual },
        { label: 'ETc المزدوج', value: result.etc_dual_mm, unit: 'مم/يوم' },
        { label: 'ETc المفرد (مقارنة)', value: result.etc_single_mm, unit: 'مم/يوم' },
      ]
    : [];

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Droplets className="w-5 h-5 text-sky-400" />
        <h2 className="text-xl font-bold text-slate-100">ETc المزدوج (FAO-56)</h2>
      </div>
      <p className="text-sm text-slate-400">
        يحسب الاستهلاك المائيّ بنهج المعامل المزدوج <span className="text-slate-300">ETc = (Kcb·Ks + Ke)·ET0</span>
        — يفصل تبخّر التربة السطحيّ (Ke) عن نتح المحصول (Kcb)، ويشتقّ Kcb
        <span className="text-slate-300"> رصداً من NDVI</span> للحقل حين يتوفّر. الطقس تُدخِله أنت.
        القيم <span className="text-amber-300">تقديريّة غير معايَرة</span>، ومصدر كلّ قيمة مُعلَن أدناه.
      </p>

      {/* Form */}
      <div className="rounded-xl border p-4 space-y-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">الحقل</span>
          <select value={fieldId} onChange={e => setFieldId(e.target.value)} className={inputCls} style={inputStyle}>
            <option value="">{fieldsLoading ? 'تحميل الحقول…' : 'اختر حقلاً'}</option>
            {options.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        </label>

        {/* الطقس */}
        <div className="rounded-lg border p-3 space-y-3" style={{ borderColor: '#334155', background: '#0f1117' }}>
          <p className="text-xs text-slate-400 font-medium">الطقس (لحساب ET0 — Penman-Monteith)</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">درجة عظمى (°م)</span>
              <input value={tMax} onChange={e => setTMax(e.target.value)} inputMode="decimal" className={inputCls} style={inputStyle} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">درجة صغرى (°م)</span>
              <input value={tMin} onChange={e => setTMin(e.target.value)} inputMode="decimal" className={inputCls} style={inputStyle} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">رطوبة (٪)</span>
              <input value={humidity} onChange={e => setHumidity(e.target.value)} inputMode="decimal" className={inputCls} style={inputStyle} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">رياح (م/ث)</span>
              <input value={wind} onChange={e => setWind(e.target.value)} inputMode="decimal" className={inputCls} style={inputStyle} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">إشعاع (م.ج/م²)</span>
              <input value={solar} onChange={e => setSolar(e.target.value)} inputMode="decimal" className={inputCls} style={inputStyle} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">خط العرض (°)</span>
              <input value={lat} onChange={e => setLat(e.target.value)} inputMode="decimal" className={inputCls} style={inputStyle} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">الارتفاع (م)</span>
              <input value={elevation} onChange={e => setElevation(e.target.value)} inputMode="decimal" className={inputCls} style={inputStyle} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">يوم السنة (1-366)</span>
              <input value={doy} onChange={e => setDoy(e.target.value)} inputMode="numeric" className={inputCls} style={inputStyle} />
            </label>
          </div>
        </div>

        {/* تجاوزات اختياريّة */}
        <div className="rounded-lg border p-3 space-y-3" style={{ borderColor: '#334155', background: '#0f1117' }}>
          <p className="text-xs text-slate-400 font-medium">تجاوزات اختياريّة (تسبق الحقن من الحقل)</p>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">NDVI (وإلّا أحدث NDVI مخزَّن للحقل)</span>
              <input value={ndviOverride} onChange={e => setNdviOverride(e.target.value)} inputMode="decimal" placeholder="من الحقل" className={inputCls} style={inputStyle} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">العمر منذ الزراعة (يوم — وإلّا من تاريخ الزراعة)</span>
              <input value={dasOverride} onChange={e => setDasOverride(e.target.value)} inputMode="numeric" placeholder="من الحقل" className={inputCls} style={inputStyle} />
            </label>
          </div>
        </div>

        <button onClick={onCompute} disabled={!fieldId || loading}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50"
          style={{ background: loading ? '#0369a1' : '#0ea5e9' }}>
          <Calculator className="w-4 h-4" /> {loading ? 'حساب…' : 'احسب'}
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
          {/* مصدر NDVI + المدخلات (شفافيّة) */}
          <div className="rounded-lg border p-3 text-xs text-slate-400 flex items-start gap-2"
            style={{ background: '#1e293b', borderColor: '#334155' }}>
            <Satellite className="w-4 h-4 mt-0.5 shrink-0 text-emerald-400" />
            <span>
              مصدر NDVI: <code className="text-slate-300">{result.ndvi.source}</code>
              {result.ndvi.used !== null && <> · القيمة <span className="text-slate-300">{result.ndvi.used}</span></>}
              {result.ndvi.date && <> · بتاريخ <span className="text-slate-300">{result.ndvi.date}</span></>}
              {' · '}المحصول <code className="text-slate-300">{result.inputs.crop_id}</code>
              {' · '}العمر <span className="text-slate-300">{result.inputs.days_after_planting}</span> يوم
              {' · '}ملوحة <span className="text-slate-300">{result.inputs.soil_ece}</span> (مصدر:{' '}
              <code className="text-slate-300">{result.inputs.soil_ece_source}</code>)
              {' · '}المرحلة <span className="text-slate-300">{result.stage}</span>
            </span>
          </div>

          {/* القيمة الرئيسة: ETc المزدوج */}
          <div className="rounded-xl border p-4 flex items-center justify-between"
            style={{ background: '#0c2a3a', borderColor: '#0ea5e9' }}>
            <div className="flex items-center gap-2">
              <Droplets className="w-5 h-5 text-sky-400" />
              <span className="text-sm text-slate-300">الاستهلاك المائيّ اليوميّ (ETc المزدوج)</span>
            </div>
            <span className="text-2xl font-bold text-sky-300">{result.etc_dual_mm} <span className="text-base text-slate-400">مم/يوم</span></span>
          </div>

          {/* جدول المعاملات */}
          <div className="rounded-xl border overflow-hidden" style={{ borderColor: '#334155' }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: '#0f1117' }}>
                  <th className="text-right px-3 py-2 text-slate-400 font-medium">المعامل</th>
                  <th className="text-center px-3 py-2 text-slate-400 font-medium">القيمة</th>
                </tr>
              </thead>
              <tbody>
                {metricRows.map((r, i) => (
                  <tr key={i} style={{ background: i % 2 ? '#1e293b' : '#172033' }}>
                    <td className="px-3 py-2 text-slate-200">{r.label}</td>
                    <td className="px-3 py-2 text-center text-slate-300">{r.value}{r.unit ? ` ${r.unit}` : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* الافتراضات (شفافيّة الصدق — لا تُخفى) */}
          {result.assumptions.length > 0 && (
            <div className="rounded-lg border p-3 text-xs space-y-1.5"
              style={{ background: '#1e293b', borderColor: '#334155' }}>
              <div className="flex items-center gap-1.5 text-slate-300 font-medium">
                <Info className="w-4 h-4 text-amber-400" /> الافتراضات (القيم تقديريّة غير معايَرة)
              </div>
              <ul className="list-disc pr-5 space-y-1 text-slate-400">
                {result.assumptions.map((a, i) => <li key={i}>{a}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
