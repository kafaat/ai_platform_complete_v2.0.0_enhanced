// ═══════════════════════════════════════════════════════════════
// SAHOOL — ScenarioComparePage (مقارنة السياسات والعائد)
// يستهلك /api/v1/crop-twin/decision/profit-aware عبر السياسات الخمس ويعرض
// الريّ/الإجهاد/الهامش لكلّ سياسة — فيرى المستخدم أثر السياسة على القرار والعائد.
// صدق: الهامش يظهر فقط مع أسعار مُمرَّرة؛ غيابها ⇒ «—» لا رقم مُختلق.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { GitCompare, AlertTriangle, TrendingUp } from 'lucide-react';
import { computeProfitAwareDecision } from '../services/api';
import type { ProfitAwareDecisionInput, ProfitAwareDecisionResult, CropDecisionForecastDay } from '../services/api';
import { ErrorState } from '../components/StateViews';

const POLICIES: { key: string; label: string }[] = [
  { key: 'water_saving',   label: 'توفير الماء' },
  { key: 'sustainability', label: 'استدامة' },
  { key: 'profit_max',     label: 'أقصى ربح' },
  { key: 'yield_max',      label: 'أقصى غلّة' },
  { key: 'risk_averse',    label: 'تجنّب المخاطرة' },
];
const TEXTURES: { key: string; label: string }[] = [
  { key: 'sand', label: 'رمليّ' }, { key: 'loam', label: 'طميّ' }, { key: 'clay', label: 'طينيّ' },
];

export default function ScenarioComparePage() {
  const [crop, setCrop] = useState('wheat');
  const [texture, setTexture] = useState('loam');
  const [rootDepth, setRootDepth] = useState('1.0');
  const [horizon, setHorizon] = useState('7');
  const [et0, setEt0] = useState('7');
  const [rain, setRain] = useState('0');
  const [target, setTarget] = useState('120');
  const [initDepletion, setInitDepletion] = useState('30');
  const [ndvi, setNdvi] = useState('0.72');
  // اقتصاد (اختياريّ — بدونه لا هامش).
  const [yieldT, setYieldT] = useState('5');
  const [cropPrice, setCropPrice] = useState('400');
  const [waterPrice, setWaterPrice] = useState('0.05');
  const [energyKwh, setEnergyKwh] = useState('500');
  const [energyPrice, setEnergyPrice] = useState('0.1');
  const [fertPrice, setFertPrice] = useState('0.8');

  const [rows, setRows] = useState<{ policy: string; res: ProfitAwareDecisionResult }[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(false);

  const numOr = (s: string, d: number): number => {
    const n = Number(s);
    return s.trim() === '' || isNaN(n) ? d : n;
  };
  const optNum = (s: string): number | null => (s.trim() === '' ? null : numOr(s, 0));

  const onCompare = () => {
    setLoading(true); setErr(false);
    const days = Math.max(1, Math.min(60, Math.round(numOr(horizon, 7))));
    const forecast: CropDecisionForecastDay[] = Array.from({ length: days }, () => ({
      t_min_c: 12, t_max_c: 32, et0_mm: numOr(et0, 7), rain_mm: numOr(rain, 0),
    }));
    const yv = optNum(yieldT);
    const cp = optNum(cropPrice);
    const yieldValue = yv != null && cp != null ? yv * cp : null;
    const base: ProfitAwareDecisionInput = {
      crop, stage: 'mid', ndvi: optNum(ndvi), forecast,
      soil: { texture, root_depth_m: numOr(rootDepth, 1.0), raw_fraction: 0.5 },
      management: { target_uptake_kg_ha: numOr(target, 0), initial_depletion_mm: numOr(initDepletion, 0) },
      auto_policy: false,
      expected_yield_t_ha: yv, crop_price_per_t: cp,
      water_price_per_m3: optNum(waterPrice), energy_kwh_ha: optNum(energyKwh),
      energy_price_per_kwh: optNum(energyPrice), fertilizer_price_per_kg: optNum(fertPrice),
      yield_value_per_ha: yieldValue,
    };
    Promise.all(POLICIES.map(p => computeProfitAwareDecision({ ...base, policy: p.key })))
      .then(rs => setRows(POLICIES.map((p, i) => ({ policy: p.key, res: rs[i] }))))
      .catch(() => { setRows(null); setErr(true); })
      .finally(() => setLoading(false));
  };

  // أفضل هامش (للإبراز) إن توفّرت الهوامش.
  const margins = (rows ?? []).map(r => r.res.economic_state.expected_margin).filter((m): m is number => m != null);
  const bestMargin = margins.length ? Math.max(...margins) : null;
  const fmt = (n: number | null | undefined): string => (n == null ? '—' : n.toFixed(0));

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <GitCompare className="w-5 h-5 text-sky-400" />
        <h2 className="text-xl font-bold text-slate-100">مقارنة السياسات والعائد</h2>
      </div>
      <p className="text-sm text-slate-400">
        نفس بيانات الحقل عبر السياسات الخمس — يُظهر أثر كلّ سياسة على الريّ والإجهاد و<span className="text-slate-300">الهامش المتوقّع</span>.
        الهامش يظهر فقط مع أسعار مُدخَلة؛ بدونها «—» (لا رقم مُختلق). كلّ القيم <span className="text-amber-300">تقديريّة غير معايَرة</span>.
      </p>

      {/* Form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <label className="flex flex-col gap-1"><span className="text-xs text-slate-400">المحصول</span>
            <input value={crop} onChange={e => setCrop(e.target.value)} className="px-3 py-2 rounded-lg text-sm"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} /></label>
          <label className="flex flex-col gap-1"><span className="text-xs text-slate-400">نسيج التربة</span>
            <select value={texture} onChange={e => setTexture(e.target.value)} className="px-3 py-2 rounded-lg text-sm"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
              {TEXTURES.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}</select></label>
          {[
            { k: 'rootDepth', label: 'عمق الجذور (م)', v: rootDepth, set: setRootDepth },
            { k: 'ndvi', label: 'NDVI', v: ndvi, set: setNdvi },
            { k: 'horizon', label: 'أفق (أيّام)', v: horizon, set: setHorizon },
            { k: 'et0', label: 'ET₀/يوم (مم)', v: et0, set: setEt0 },
            { k: 'rain', label: 'مطر/يوم (مم)', v: rain, set: setRain },
            { k: 'target', label: 'هدف الامتصاص (كجم/ها)', v: target, set: setTarget },
            { k: 'init', label: 'استنزاف ابتدائيّ (مم)', v: initDepletion, set: setInitDepletion },
          ].map(f => (
            <label key={f.k} className="flex flex-col gap-1"><span className="text-xs text-slate-400">{f.label}</span>
              <input type="number" inputMode="decimal" step="any" value={f.v} onChange={e => f.set(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} /></label>
          ))}
        </div>
        <div className="text-[11px] text-slate-500 pt-1">مدخلات اقتصاديّة (اختياريّة — للهامش):</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[
            { k: 'yieldT', label: 'الغلّة المتوقّعة (طن/ها)', v: yieldT, set: setYieldT },
            { k: 'cropPrice', label: 'سعر المحصول (/طن)', v: cropPrice, set: setCropPrice },
            { k: 'waterPrice', label: 'سعر الماء (/م³)', v: waterPrice, set: setWaterPrice },
            { k: 'energyKwh', label: 'طاقة (kWh/ها)', v: energyKwh, set: setEnergyKwh },
            { k: 'energyPrice', label: 'سعر الطاقة (/kWh)', v: energyPrice, set: setEnergyPrice },
            { k: 'fertPrice', label: 'سعر السماد (/كجم)', v: fertPrice, set: setFertPrice },
          ].map(f => (
            <label key={f.k} className="flex flex-col gap-1"><span className="text-xs text-slate-400">{f.label}</span>
              <input type="number" inputMode="decimal" step="any" value={f.v} onChange={e => f.set(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} /></label>
          ))}
        </div>
        <div className="flex justify-end">
          <button onClick={onCompare} disabled={loading}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#0ea5e9' }}>
            <GitCompare className="w-4 h-4" />
            {loading ? 'جارٍ المقارنة…' : 'قارن السياسات'}
          </button>
        </div>
      </div>

      {err && <ErrorState title="تعذّرت المقارنة" onRetry={onCompare} />}

      {rows && (
        <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[11px] text-slate-400" style={{ borderBottom: '1px solid #334155' }}>
                <th className="px-3 py-2 text-right font-medium">السياسة</th>
                <th className="px-3 py-2 text-right font-medium">الريّ (مم)</th>
                <th className="px-3 py-2 text-right font-medium">م³/ها</th>
                <th className="px-3 py-2 text-right font-medium">أيّام إجهاد</th>
                <th className="px-3 py-2 text-right font-medium">الهامش المتوقّع</th>
                <th className="px-3 py-2 text-right font-medium">± عدم اليقين</th>
                <th className="px-3 py-2 text-right font-medium">الثقة</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const e = row.res.economic_state;
                const isBest = bestMargin != null && e.expected_margin === bestMargin;
                return (
                  <tr key={i} className="text-slate-300" style={{ borderBottom: '1px solid #25303f', background: isBest ? '#0c2233' : undefined }}>
                    <td className="px-3 py-1.5">
                      {POLICIES.find(p => p.key === row.policy)?.label ?? row.policy}
                      {isBest && <TrendingUp className="inline w-3.5 h-3.5 text-emerald-400 mr-1" />}
                    </td>
                    <td className="px-3 py-1.5">{row.res.irrigation.total_mm.toFixed(0)}</td>
                    <td className="px-3 py-1.5">{(row.res.irrigation.total_mm * 10).toFixed(0)}</td>
                    <td className="px-3 py-1.5">{row.res.irrigation.stress_days}</td>
                    <td className="px-3 py-1.5 font-semibold text-slate-100">{fmt(e.expected_margin)}</td>
                    <td className="px-3 py-1.5 text-slate-400">{e.margin_uncertainty == null ? '—' : `±${e.margin_uncertainty.toFixed(0)}`}</td>
                    <td className="px-3 py-1.5">{e.confidence == null ? '—' : `${(e.confidence * 100).toFixed(0)}٪`}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="flex items-start gap-2 px-4 py-3" style={{ borderTop: '1px solid #334155' }}>
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="text-[11px] text-amber-300/80">
              قيم تقديريّة غير معايَرة (±20٪). الهامش يحتاج أسعاراً مُدخَلة؛ «أقصى ربح» يحتاج سعر الماء وقيمة الغلّة وإلّا يتراجع لتوفير الماء.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
