// ═══════════════════════════════════════════════════════════════
// SAHOOL — IrrigationPlanPage (ربط حيّ بـ POST /api/v1/irrigation-plan)
// خطّ «مركز المحاصيل»: نسيج التربة + عمق ⇒ TAW ⇒ سياسة قرار ⇒ جدول ريّ للأيّام القادمة
// (FAO-56، ميزان منطقة الجذور). صدق: كلّ القيم موسومة «غير معايَرة» — تقدير لا قياس.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Droplets, CalendarRange, AlertTriangle, CloudRain } from 'lucide-react';
import { useComputeIrrigationPlan } from '../hooks/useApi';
import type { IrrigationPlanInput, ForecastDayInput } from '../services/api';
import { ErrorState } from '../components/StateViews';

const POLICIES: { key: string; label: string }[] = [
  { key: 'water_saving',   label: 'توفير الماء (ريّ عجزيّ)' },
  { key: 'yield_max',      label: 'أقصى غلّة' },
  { key: 'profit_max',     label: 'أقصى ربح (يحتاج أسعاراً)' },
  { key: 'sustainability', label: 'استدامة (حفظ الخزّان)' },
  { key: 'risk_averse',    label: 'تجنّب المخاطرة' },
];

const TEXTURES: { key: string; label: string }[] = [
  { key: 'sand',        label: 'رمليّ' },
  { key: 'sandy_loam',  label: 'طميّ-رمليّ' },
  { key: 'loam',        label: 'طميّ' },
  { key: 'clay_loam',   label: 'طميّ-طينيّ' },
  { key: 'silty_clay',  label: 'طينيّ-سلتيّ' },
  { key: 'clay',        label: 'طينيّ' },
];

const POLICY_LABEL: Record<string, string> = Object.fromEntries(POLICIES.map(p => [p.key, p.label]));

export default function IrrigationPlanPage() {
  const mut = useComputeIrrigationPlan();
  // مدخلات مبسّطة: تنبّؤ موحّد (نفس القيم لكلّ يوم) + خصائص التربة والسياسة.
  const [horizon, setHorizon] = useState('7');
  const [et0, setEt0] = useState('6');
  const [kc, setKc] = useState('1.0');
  const [rain, setRain] = useState('0');
  const [texture, setTexture] = useState('loam');
  const [rootDepth, setRootDepth] = useState('1.0');
  const [p, setP] = useState('0.5');
  const [policy, setPolicy] = useState('water_saving');
  const [initDepletion, setInitDepletion] = useState('0');
  const [budget, setBudget] = useState('');

  const numOr = (s: string, d: number): number => {
    const n = Number(s);
    return s.trim() === '' || isNaN(n) ? d : n;
  };

  const onCompute = () => {
    const days = Math.max(1, Math.min(60, Math.round(numOr(horizon, 7))));
    const forecast: ForecastDayInput[] = Array.from({ length: days }, () => ({
      et0_mm: numOr(et0, 6),
      kc: numOr(kc, 1.0),
      rain_mm: numOr(rain, 0),
    }));
    const payload: IrrigationPlanInput = {
      forecast,
      soil_texture: texture,
      root_depth_m: numOr(rootDepth, 1.0),
      raw_fraction: numOr(p, 0.5),
      policy,
      initial_depletion_mm: numOr(initDepletion, 0),
      season_budget_mm: budget.trim() === '' ? null : numOr(budget, 0),
    };
    mut.mutate(payload);
  };

  const res = mut.data;

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <CalendarRange className="w-5 h-5 text-sky-400" />
        <h2 className="text-xl font-bold text-slate-100">خطّة الريّ المتنبّأ بها</h2>
      </div>
      <p className="text-sm text-slate-400">
        يحسب جدول الريّ للأيّام القادمة عبر خطّ «مركز المحاصيل»: نسيج التربة وعمق الجذور
        يحدّدان الماء المتاح (TAW)، والسياسة تحدّد <span className="text-slate-300">كيف نتصرّف</span> تجاه
        الاحتياج، والمُخطِّط يوزّع الريّ على الأيّام مع احترام المطر المتوقّع.
        كلّ القيم <span className="text-amber-300">تقديريّة غير معايَرة يمنيّاً</span> (calibrated=false).
      </p>

      {/* Form */}
      <div className="rounded-xl border p-4 space-y-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">السياسة (الهدف)</span>
            <select value={policy} onChange={e => setPolicy(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
              {POLICIES.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">نسيج التربة</span>
            <select value={texture} onChange={e => setTexture(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
              {TEXTURES.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </label>
          {[
            { k: 'rootDepth', label: 'عمق الجذور (م)', v: rootDepth, set: setRootDepth },
            { k: 'p', label: 'نسبة الاستنفاد p', v: p, set: setP },
            { k: 'horizon', label: 'أفق التنبّؤ (أيّام)', v: horizon, set: setHorizon },
            { k: 'et0', label: 'ET₀ يوميّ (مم)', v: et0, set: setEt0 },
            { k: 'kc', label: 'معامل المحصول Kc', v: kc, set: setKc },
            { k: 'rain', label: 'مطر متوقّع/يوم (مم)', v: rain, set: setRain },
            { k: 'init', label: 'استنزاف ابتدائيّ (مم)', v: initDepletion, set: setInitDepletion },
            { k: 'budget', label: 'ميزانيّة الموسم (مم، اختياريّ)', v: budget, set: setBudget },
          ].map(f => (
            <label key={f.k} className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">{f.label}</span>
              <input type="number" inputMode="decimal" step="any" value={f.v}
                onChange={e => f.set(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
          ))}
        </div>
        <p className="text-[11px] text-slate-500">
          تنبّؤ مبسّط موحّد (نفس ET₀/Kc/المطر لكلّ يوم) للتجربة — سيُربط لاحقاً بتنبّؤ جوّيّ يوميّ فعليّ.
        </p>
        <div className="flex justify-end">
          <button onClick={onCompute} disabled={mut.isPending}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#0ea5e9' }}>
            <Droplets className="w-4 h-4" />
            {mut.isPending ? 'جارٍ حساب الجدول…' : 'احسب خطّة الريّ'}
          </button>
        </div>
      </div>

      {mut.isError && <ErrorState title="تعذّر حساب خطّة الريّ" onRetry={onCompute} />}

      {/* Results */}
      {res && (
        <div className="space-y-4">
          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'الماء المتاح TAW (مم)', v: res.plan.taw_mm.toFixed(1) },
              { label: 'الماء المتاح بيُسر RAW (مم)', v: res.plan.raw_mm.toFixed(1) },
              { label: 'إجمالي الريّ (مم)', v: res.plan.total_irrigation_mm.toFixed(1) },
              { label: 'إجمالي الريّ (م³/هكتار)', v: res.plan.total_irrigation_m3_ha.toFixed(0) },
              { label: 'عدد دفعات الريّ', v: String(res.plan.n_events) },
              { label: 'أيّام الإجهاد', v: String(res.plan.stress_days.length) },
              { label: 'الاستنزاف النهائيّ (مم)', v: res.plan.final_depletion_mm.toFixed(1) },
              { label: 'التسرّب العميق (مم)', v: res.plan.total_deep_perc_mm.toFixed(1) },
            ].map((x, i) => (
              <div key={i} className="rounded-xl p-3 border text-center" style={{ background: '#1e293b', borderColor: '#334155' }}>
                <div className="text-[11px] text-slate-400 mb-1">{x.label}</div>
                <div className="text-lg font-bold text-slate-100">{x.v}</div>
              </div>
            ))}
          </div>

          {/* Policy + honesty banner */}
          <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="text-sm font-semibold text-slate-100">
                السياسة المطبَّقة: {POLICY_LABEL[res.plan.policy] ?? res.plan.policy}
                {res.plan.budget_exhausted && <span className="text-orange-300"> · نفدت ميزانيّة الموسم</span>}
              </div>
              <div className="text-[11px] text-amber-300/90">
                ⚠ قيم تقديريّة غير معايَرة يمنيّاً (calibrated={String(res.plan.calibrated)}) — للإرشاد لا للقرار النهائيّ.
              </div>
              {res.plan.notes_ar.map((n, i) => (
                <div key={i} className="text-[11px] text-slate-400">• {n}</div>
              ))}
              {res.soil.warnings_ar.map((n, i) => (
                <div key={`s${i}`} className="text-[11px] text-slate-500">• {n}</div>
              ))}
            </div>
          </div>

          {/* Days table */}
          <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[11px] text-slate-400" style={{ borderBottom: '1px solid #334155' }}>
                  <th className="px-3 py-2 text-right font-medium">اليوم</th>
                  <th className="px-3 py-2 text-right font-medium">ETc</th>
                  <th className="px-3 py-2 text-right font-medium">مطر فعّال</th>
                  <th className="px-3 py-2 text-right font-medium">استنزاف قبل</th>
                  <th className="px-3 py-2 text-right font-medium">ريّ</th>
                  <th className="px-3 py-2 text-right font-medium">استنزاف بعد</th>
                  <th className="px-3 py-2 text-right font-medium">الحالة</th>
                </tr>
              </thead>
              <tbody>
                {res.plan.days.map(d => {
                  const deferredByRain = d.eff_rain_mm > 0 && d.irrigation_mm === 0;
                  return (
                    <tr key={d.day_index} className="text-slate-300"
                      style={{ borderBottom: '1px solid #25303f', background: d.stressed ? '#2a0d0d' : undefined }}>
                      <td className="px-3 py-1.5">{d.day_index + 1}</td>
                      <td className="px-3 py-1.5">{d.etc_mm.toFixed(1)}</td>
                      <td className="px-3 py-1.5">
                        {d.eff_rain_mm > 0
                          ? <span className="inline-flex items-center gap-1 text-sky-300"><CloudRain className="w-3.5 h-3.5" />{d.eff_rain_mm.toFixed(1)}</span>
                          : '—'}
                      </td>
                      <td className="px-3 py-1.5">{d.dr_before_irrig_mm.toFixed(1)}</td>
                      <td className="px-3 py-1.5 font-semibold text-slate-100">{d.irrigation_mm > 0 ? d.irrigation_mm.toFixed(1) : '—'}</td>
                      <td className="px-3 py-1.5">{d.dr_end_mm.toFixed(1)}</td>
                      <td className="px-3 py-1.5 text-xs">
                        {d.stressed
                          ? <span className="text-orange-300">إجهاد</span>
                          : deferredByRain
                            ? <span className="text-sky-300">أُجّل (مطر)</span>
                            : d.irrigation_mm > 0
                              ? <span className="text-emerald-300">ريّ</span>
                              : <span className="text-slate-500">—</span>}
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
